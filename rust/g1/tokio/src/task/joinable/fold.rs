use std::ops::ControlFlow;

use crate::task::join_guard::ShutdownError;

use super::Joinable;
use super::try_fold::{TryFold, TryFoldFn, try_fold};

pub trait FoldFn<J: Joinable, B> = FnMut(
    Result<B, ShutdownError>,
    Result<<J as Joinable>::Output, ShutdownError>,
) -> Result<B, ShutdownError>;

pub type Fold<J, const N: usize, B, F>
    = TryFold<J, N, B, Folder<J, B, F>>
where
    J: Joinable + Unpin,
    F: FoldFn<J, B>;

pub type Folder<J, B, F>
    = impl TryFoldFn<J, B>
where
    J: Joinable,
    F: FoldFn<J, B>;

pub fn fold<J, const N: usize, B, F>(joinables: [J; N], init: B, f: F) -> Fold<J, N, B, F>
where
    J: Joinable + Unpin,
    F: FoldFn<J, B>,
{
    try_fold(joinables, init, folder(f))
}

#[define_opaque(Folder)]
fn folder<J, B, F>(mut f: F) -> Folder<J, B, F>
where
    J: Joinable,
    F: FoldFn<J, B>,
{
    move |acc, result| ControlFlow::Continue(f(acc, result))
}

#[cfg(test)]
mod tests {
    use std::future;
    use std::sync::Arc;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::time::Duration;

    use tokio::time;

    use crate::task::join_guard::JoinGuard;

    use super::*;

    #[derive(Clone)]
    struct Counter(Arc<AtomicUsize>);

    impl Counter {
        fn new() -> Self {
            Self(Arc::new(AtomicUsize::new(0)))
        }

        fn get(&self) -> usize {
            self.0.load(Ordering::SeqCst)
        }

        fn inc(&self) -> usize {
            self.0.fetch_add(1, Ordering::SeqCst)
        }
    }

    // TODO: Can we write this test without using `time::sleep`?
    #[tokio::test]
    async fn test_fold() {
        let num_joined = Counter::new();
        let num_dropped = Counter::new();
        let mut j = fold(
            [
                JoinGuard::spawn(|_| {
                    let num_dropped = num_dropped.clone();
                    async move {
                        scopeguard::defer! {
                            num_dropped.inc();
                        }
                        future::pending().await
                    }
                }),
                JoinGuard::spawn(|_| {
                    let num_joined = num_joined.clone();
                    let num_dropped = num_dropped.clone();
                    async move {
                        scopeguard::defer! {
                            num_dropped.inc();
                        }
                        num_joined.inc();
                    }
                }),
            ],
            (),
            |_, result| result,
        );

        assert_eq!(num_joined.get(), 0);
        assert_eq!(num_dropped.get(), 0);

        assert!(
            time::timeout(Duration::from_millis(5), &mut j)
                .await
                .is_err(),
        );
        assert_eq!(num_joined.get(), 1);
        assert_eq!(num_dropped.get(), 1);

        assert_eq!(
            j.shutdown_with_timeout(Duration::ZERO).await,
            Err(ShutdownError::JoinTimeout),
        );
        time::sleep(Duration::from_millis(5)).await;
        assert_eq!(num_joined.get(), 1);
        assert_eq!(num_dropped.get(), 2);
    }
}
