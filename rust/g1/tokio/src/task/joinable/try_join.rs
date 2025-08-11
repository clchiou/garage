use std::ops::ControlFlow;

use crate::task::join_guard::ShutdownError;

use super::Joinable;
use super::try_fold::{TryFold, TryFoldFn, try_fold};

pub type TryJoin<J, const N: usize, E>
    = TryFold<J, N, Result<(), E>, TryJoiner<J, E>>
where
    J: Joinable<Output = Result<(), E>> + Unpin;

pub type TryJoiner<J, E>
    = impl TryFoldFn<J, Result<(), E>>
where
    J: Joinable<Output = Result<(), E>>;

#[define_opaque(TryJoiner)]
pub fn try_join<J, const N: usize, E>(joinables: [J; N]) -> TryJoin<J, N, E>
where
    J: Joinable<Output = Result<(), E>> + Unpin,
{
    try_fold(joinables, Ok(()), try_joiner)
}

pub type TryJoinerReturn<E> =
    ControlFlow<Result<Result<(), E>, ShutdownError>, Result<Result<(), E>, ShutdownError>>;

// I am not sure about the details yet, but for now, the priority is as follows:
// ```
// E > TaskAborted > JoinTimeout > Ok
// ```
fn try_joiner<E>(
    acc: Result<Result<(), E>, ShutdownError>,
    result: Result<Result<(), E>, ShutdownError>,
) -> TryJoinerReturn<E> {
    ControlFlow::Break(match (acc, result) {
        (next_acc @ Ok(Err(_)), _) => next_acc,
        (_, next_acc @ Ok(Err(_))) => next_acc,

        (next_acc @ Err(ShutdownError::TaskAborted), _) => next_acc,
        (_, next_acc @ Err(ShutdownError::TaskAborted)) => next_acc,

        (next_acc @ Err(ShutdownError::JoinTimeout), _) => next_acc,
        (_, next_acc @ Err(ShutdownError::JoinTimeout)) => next_acc,

        (Ok(Ok(())), Ok(Ok(()))) => return ControlFlow::Continue(Ok(Ok(()))),
    })
}

#[cfg(test)]
mod tests {
    use std::future;
    use std::time::Duration;

    use crate::task::join_guard::{Cancel, JoinGuard};

    use super::*;

    #[tokio::test]
    async fn test_try_join() {
        fn aborted() -> JoinGuard<Result<(), &'static str>> {
            let handle = tokio::spawn(future::pending());
            handle.abort();
            JoinGuard::new(handle, Cancel::new())
        }

        let mut j = try_join::<_, 1, &'static str>([JoinGuard::spawn(|_| future::ready(Ok(())))]);
        assert_eq!(j.shutdown_with_timeout(Duration::ZERO).await, Ok(Ok(())));

        let mut j = try_join::<_, 2, &'static str>([
            JoinGuard::spawn(|_| future::ready(Ok(()))),
            JoinGuard::spawn(|_| future::pending()),
        ]);
        assert_eq!(
            j.shutdown_with_timeout(Duration::ZERO).await,
            Err(ShutdownError::JoinTimeout),
        );

        let mut j = try_join::<_, 3, &'static str>([
            JoinGuard::spawn(|_| future::ready(Ok(()))),
            JoinGuard::spawn(|_| future::pending()),
            aborted(),
        ]);
        assert_eq!(
            j.shutdown_with_timeout(Duration::ZERO).await,
            Err(ShutdownError::TaskAborted),
        );

        let mut j = try_join::<_, 2, &'static str>([
            aborted(),
            JoinGuard::spawn(|_| future::ready(Err("foo"))),
        ]);
        assert_eq!(
            j.shutdown_with_timeout(Duration::ZERO).await,
            Err(ShutdownError::TaskAborted),
        );

        let mut j = try_join::<_, 2, &'static str>([
            JoinGuard::spawn(|_| future::ready(Err("foo"))),
            aborted(),
        ]);
        assert_eq!(
            j.shutdown_with_timeout(Duration::ZERO).await,
            Ok(Err("foo")),
        );
    }
}
