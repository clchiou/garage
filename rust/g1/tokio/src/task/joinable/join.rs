use crate::task::join_guard::ShutdownError;

use super::Joinable;
use super::fold::{Fold, FoldFn, fold};

pub type Join<J, const N: usize, E>
    = Fold<J, N, Result<(), E>, Joiner<J, E>>
where
    J: Joinable<Output = Result<(), E>> + Unpin;

pub type Joiner<J, E>
    = impl FoldFn<J, Result<(), E>>
where
    J: Joinable<Output = Result<(), E>>;

#[define_opaque(Joiner)]
pub fn join<J, const N: usize, E>(joinables: [J; N]) -> Join<J, N, E>
where
    J: Joinable<Output = Result<(), E>> + Unpin,
{
    fold(joinables, Ok(()), joiner)
}

// I am not sure about the details yet, but for now, the priority is as follows:
// ```
// E > TaskAborted > JoinTimeout > Ok
// ```
fn joiner<E>(
    acc: Result<Result<(), E>, ShutdownError>,
    result: Result<Result<(), E>, ShutdownError>,
) -> Result<Result<(), E>, ShutdownError> {
    match (acc, result) {
        (next_acc @ Ok(Err(_)), _) => next_acc,
        (_, next_acc @ Ok(Err(_))) => next_acc,

        (next_acc @ Err(ShutdownError::TaskAborted), _) => next_acc,
        (_, next_acc @ Err(ShutdownError::TaskAborted)) => next_acc,

        (next_acc @ Err(ShutdownError::JoinTimeout), _) => next_acc,
        (_, next_acc @ Err(ShutdownError::JoinTimeout)) => next_acc,

        (Ok(Ok(())), Ok(Ok(()))) => Ok(Ok(())),
    }
}

#[cfg(test)]
mod tests {
    use std::future;
    use std::time::Duration;

    use crate::task::join_guard::{Cancel, JoinGuard};

    use super::*;

    #[tokio::test]
    async fn test_join() {
        fn aborted() -> JoinGuard<Result<(), &'static str>> {
            let handle = tokio::spawn(future::pending());
            handle.abort();
            JoinGuard::new(handle, Cancel::new())
        }

        let mut j = join::<_, 1, &'static str>([JoinGuard::spawn(|_| future::ready(Ok(())))]);
        assert_eq!(j.shutdown_with_timeout(Duration::ZERO).await, Ok(Ok(())));

        let mut j = join::<_, 2, &'static str>([
            JoinGuard::spawn(|_| future::ready(Ok(()))),
            JoinGuard::spawn(|_| future::pending()),
        ]);
        assert_eq!(
            j.shutdown_with_timeout(Duration::ZERO).await,
            Err(ShutdownError::JoinTimeout),
        );

        let mut j = join::<_, 3, &'static str>([
            JoinGuard::spawn(|_| future::ready(Ok(()))),
            JoinGuard::spawn(|_| future::pending()),
            aborted(),
        ]);
        assert_eq!(
            j.shutdown_with_timeout(Duration::ZERO).await,
            Err(ShutdownError::TaskAborted),
        );

        let mut j = join::<_, 4, &'static str>([
            JoinGuard::spawn(|_| future::ready(Ok(()))),
            JoinGuard::spawn(|_| future::pending()),
            aborted(),
            JoinGuard::spawn(|_| future::ready(Err("foo"))),
        ]);
        assert_eq!(
            j.shutdown_with_timeout(Duration::ZERO).await,
            Ok(Err("foo")),
        );
    }
}
