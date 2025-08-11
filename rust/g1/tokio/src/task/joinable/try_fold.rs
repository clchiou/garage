use std::future::{self, Future};
use std::mem;
use std::ops::ControlFlow;
use std::pin::Pin;
use std::task::{Context, Poll};
use std::time::Duration;

use async_trait::async_trait;
use tokio::time::{self, Instant};

use g1_base::future::ReadyArray;

use crate::task::join_guard::{Cancel, ShutdownError};

use super::Joinable;

pub trait TryFoldFn<J: Joinable, B> =
    FnMut(
        Result<B, ShutdownError>,
        Result<<J as Joinable>::Output, ShutdownError>,
    ) -> ControlFlow<Result<B, ShutdownError>, Result<B, ShutdownError>>;

#[derive(Debug)]
pub struct TryFold<J: Joinable + Unpin, const N: usize, B, F>(TryFoldInner<J, N, B, F>);

#[derive(Debug)]
enum TryFoldInner<J, const N: usize, B, F>
where
    J: Joinable + Unpin,
{
    Running {
        joinables: ReadyArray<J, N>,
        acc: Option<Result<B, ShutdownError>>,
        f: F,
    },
    Finished(Result<B, ShutdownError>),
    Consumed,
}

pub fn try_fold<J, const N: usize, B, F>(joinables: [J; N], init: B, f: F) -> TryFold<J, N, B, F>
where
    J: Joinable + Unpin,
    F: TryFoldFn<J, B>,
{
    TryFold::new(joinables, init, f)
}

impl<J, const N: usize, B, F> TryFold<J, N, B, F>
where
    J: Joinable + Unpin,
{
    pub fn new(joinables: [J; N], init: B, f: F) -> Self {
        Self(TryFoldInner::new(joinables, init, f))
    }
}

impl<J, const N: usize, B, F> Future for TryFold<J, N, B, F>
where
    J: Joinable + Unpin,
    B: Unpin,
    F: TryFoldFn<J, B> + Unpin,
{
    type Output = ();

    fn poll(mut self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
        self.0.poll(context)
    }
}

#[async_trait]
impl<J, const N: usize, B, F> Joinable for TryFold<J, N, B, F>
where
    J: Joinable + Send + Unpin,
    B: Send + Unpin,
    F: TryFoldFn<J, B> + Send + Unpin,
{
    type Output = B;

    fn add_parent(&self, parent: Cancel) {
        self.0
            .iter()
            .for_each(|joinable| joinable.add_parent(parent.clone()))
    }

    fn add_timeout(&self, timeout: Duration) {
        self.0
            .iter()
            .for_each(|joinable| joinable.add_timeout(timeout))
    }

    fn add_deadline(&self, deadline: Instant) {
        self.0
            .iter()
            .for_each(|joinable| joinable.add_deadline(deadline))
    }

    fn cancel(&self) {
        self.0.iter().for_each(|joinable| joinable.cancel())
    }

    async fn shutdown_with_timeout(
        &mut self,
        timeout: Duration,
    ) -> Result<<Self as Joinable>::Output, ShutdownError> {
        self.cancel();

        if time::timeout(timeout, future::poll_fn(|cx| self.0.poll(cx)))
            .await
            .is_err()
        {
            let (mut joinables, acc, mut f) = self.0.take_running();
            drop(joinables.detach_all());
            return f(acc, Err(ShutdownError::JoinTimeout)).into_value();
        }

        self.take_result()
    }

    fn take_result(&mut self) -> Result<<Self as Joinable>::Output, ShutdownError> {
        self.0.take_result()
    }
}

impl<J, const N: usize, B, F> TryFoldInner<J, N, B, F>
where
    J: Joinable + Unpin,
{
    fn new(joinables: [J; N], init: B, f: F) -> Self {
        Self::Running {
            joinables: ReadyArray::new(joinables),
            acc: Some(Ok(init)),
            f,
        }
    }

    fn iter(&self) -> impl Iterator<Item = &J> {
        match self {
            Self::Running { joinables, .. } => Some(joinables.iter()),
            _ => None,
        }
        .into_iter()
        .flatten()
    }

    fn take_running(&mut self) -> (ReadyArray<J, N>, Result<B, ShutdownError>, F) {
        match mem::replace(self, Self::Consumed) {
            Self::Running { joinables, acc, f } => (joinables, acc.expect("acc"), f),
            Self::Finished(_) => panic!("fold was finished"),
            Self::Consumed => panic!("fold has been consumed already"),
        }
    }

    fn take_result(&mut self) -> Result<B, ShutdownError> {
        match mem::replace(self, Self::Consumed) {
            Self::Running { mut joinables, .. } => {
                drop(joinables.detach_all());
                panic!("fold is still running; abort")
            }
            Self::Finished(result) => result,
            Self::Consumed => panic!("fold result was consumed"),
        }
    }
}

impl<J, const N: usize, B, F> TryFoldInner<J, N, B, F>
where
    J: Joinable + Unpin,
    F: TryFoldFn<J, B>,
{
    fn poll(&mut self, context: &mut Context<'_>) -> Poll<()> {
        let Self::Running { joinables, acc, f } = self else {
            return Poll::Ready(());
        };

        let mut a = acc.take().expect("acc");
        while !joinables.is_empty() {
            if joinables.poll_ready(context) == Poll::Pending {
                *acc = Some(a);
                return Poll::Pending;
            }
            while let Some(((), mut joinable)) = joinables.try_pop_ready_with_future() {
                let flow = f(a, joinable.take_result());
                if flow.is_break() {
                    drop(joinables.detach_all());
                }
                a = flow.into_value();
            }
        }

        *self = Self::Finished(a);
        Poll::Ready(())
    }
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
    async fn test_try_fold() {
        let num_joined = Counter::new();
        let num_dropped = Counter::new();
        let mut j = try_fold(
            [
                JoinGuard::spawn(|_| {
                    let num_joined = num_joined.clone();
                    let num_dropped = num_dropped.clone();
                    async move {
                        scopeguard::defer! {
                            num_dropped.inc();
                        }
                        time::sleep(Duration::from_millis(5)).await;
                        num_joined.inc();
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
            |_, result| ControlFlow::Break(result),
        );

        assert!(matches!(j.0, TryFoldInner::Running { .. }));
        assert_eq!(num_joined.get(), 0);
        assert_eq!(num_dropped.get(), 0);

        assert_eq!(
            j.shutdown_with_timeout(Duration::from_millis(10)).await,
            Ok(()),
        );
        assert!(matches!(j.0, TryFoldInner::Consumed));
        time::sleep(Duration::from_millis(5)).await;
        assert_eq!(num_joined.get(), 1);
        assert_eq!(num_dropped.get(), 2);
    }

    #[tokio::test]
    async fn shutdown_timeout() {
        let mut j = try_fold(
            [JoinGuard::spawn(|_| future::pending())],
            (),
            |_, result| ControlFlow::Continue(result),
        );
        assert_eq!(
            j.shutdown_with_timeout(Duration::ZERO).await,
            Err(ShutdownError::JoinTimeout),
        );
        assert!(matches!(j.0, TryFoldInner::Consumed));
    }
}
