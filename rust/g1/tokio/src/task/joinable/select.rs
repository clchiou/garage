use std::ops::ControlFlow;

use crate::task::join_guard::ShutdownError;

use super::Joinable;
use super::try_fold::{TryFold, TryFoldFn, try_fold};

pub type Select<J, const N: usize, E>
    = TryFold<J, N, Result<(), E>, Selector<J, E>>
where
    J: Joinable<Output = Result<(), E>> + Unpin;

pub type Selector<J, E>
    = impl TryFoldFn<J, Result<(), E>>
where
    J: Joinable<Output = Result<(), E>>;

#[define_opaque(Selector)]
pub fn select<J, const N: usize, E>(joinables: [J; N]) -> Select<J, N, E>
where
    J: Joinable<Output = Result<(), E>> + Unpin,
{
    try_fold(joinables, Ok(()), selector)
}

pub type SelectorReturn<E> =
    ControlFlow<Result<Result<(), E>, ShutdownError>, Result<Result<(), E>, ShutdownError>>;

fn selector<E>(
    acc: Result<Result<(), E>, ShutdownError>,
    result: Result<Result<(), E>, ShutdownError>,
) -> SelectorReturn<E> {
    assert!(matches!(acc, Ok(Ok(()))));
    ControlFlow::Break(result)
}

#[cfg(test)]
mod tests {
    use std::future;
    use std::time::Duration;

    use crate::task::join_guard::{Cancel, JoinGuard};

    use super::*;

    fn aborted() -> JoinGuard<Result<(), &'static str>> {
        let handle = tokio::spawn(future::pending());
        handle.abort();
        JoinGuard::new(handle, Cancel::new())
    }

    #[tokio::test]
    async fn test_select() {
        let mut j = select::<JoinGuard<Result<(), &'static str>>, 0, &'static str>([]);
        (&mut j).await;
        assert_eq!(j.take_result(), Ok(Ok(())));

        let mut j = select::<_, 1, &'static str>([JoinGuard::spawn(|_| future::ready(Ok(())))]);
        (&mut j).await;
        assert_eq!(j.take_result(), Ok(Ok(())));

        let mut j = select::<_, 2, &'static str>([
            JoinGuard::spawn(|_| future::pending()),
            JoinGuard::spawn(|_| future::ready(Ok(()))),
        ]);
        (&mut j).await;
        assert_eq!(j.take_result(), Ok(Ok(())));

        let mut j = select::<_, 2, &'static str>([
            JoinGuard::spawn(|_| future::pending()),
            JoinGuard::spawn(|_| future::ready(Err("foo"))),
        ]);
        (&mut j).await;
        assert_eq!(j.take_result(), Ok(Err("foo")));

        let mut j =
            select::<_, 2, &'static str>([JoinGuard::spawn(|_| future::pending()), aborted()]);
        (&mut j).await;
        assert_eq!(j.take_result(), Err(ShutdownError::TaskAborted));
    }

    #[tokio::test]
    async fn select_shutdown() {
        let mut j = select::<JoinGuard<Result<(), &'static str>>, 0, &'static str>([]);
        assert_eq!(j.shutdown_with_timeout(Duration::ZERO).await, Ok(Ok(())));

        let mut j = select::<_, 1, &'static str>([JoinGuard::spawn(|_| future::ready(Ok(())))]);
        assert_eq!(j.shutdown_with_timeout(Duration::ZERO).await, Ok(Ok(())));

        let mut j = select::<_, 2, &'static str>([
            JoinGuard::spawn(|_| future::pending()),
            JoinGuard::spawn(|_| future::ready(Ok(()))),
        ]);
        assert_eq!(j.shutdown_with_timeout(Duration::ZERO).await, Ok(Ok(())));

        let mut j = select::<_, 2, &'static str>([
            JoinGuard::spawn(|_| future::pending()),
            JoinGuard::spawn(|_| future::ready(Err("foo"))),
        ]);
        assert_eq!(
            j.shutdown_with_timeout(Duration::ZERO).await,
            Ok(Err("foo")),
        );

        let mut j =
            select::<_, 2, &'static str>([JoinGuard::spawn(|_| future::pending()), aborted()]);
        assert_eq!(
            j.shutdown_with_timeout(Duration::ZERO).await,
            Err(ShutdownError::TaskAborted),
        );

        let mut j = select::<_, 1, &'static str>([JoinGuard::spawn(|_| future::pending())]);
        assert_eq!(
            j.shutdown_with_timeout(Duration::ZERO).await,
            Err(ShutdownError::JoinTimeout),
        );
    }
}
