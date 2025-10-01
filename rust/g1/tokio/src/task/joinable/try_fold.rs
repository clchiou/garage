use std::future::{self, Future};
use std::mem;
use std::ops::ControlFlow;
use std::pin::Pin;
use std::task::{self, Context, Poll};
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
pub struct TryFold<J, const N: usize, B, F>
where
    J: Joinable + Unpin,
{
    joinables: ReadyArray<J, N>,
    state: State<B, F>,
}

#[derive(Debug)]
enum State<B, F> {
    Running {
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
        Self {
            joinables: ReadyArray::new(joinables),
            state: State::Running {
                acc: Some(Ok(init)),
                f,
            },
        }
    }
}

impl<J, const N: usize, B, F> TryFold<J, N, B, F>
where
    J: Joinable + Unpin,
    F: TryFoldFn<J, B>,
{
    fn poll_try_fold(&mut self, context: &mut Context<'_>) -> Poll<()> {
        let State::Running { acc, f } = &mut self.state else {
            return Poll::Ready(());
        };

        let mut a = acc.take().expect("acc");
        'outer: while !self.joinables.is_empty() {
            if self.joinables.poll_ready(context) == Poll::Pending {
                *acc = Some(a);
                return Poll::Pending;
            }
            while let Some(((), mut joinable)) = self.joinables.try_pop_ready_with_future() {
                let flow = f(a, joinable.take_result());
                let is_break = flow.is_break();
                a = flow.into_value();
                if is_break {
                    break 'outer;
                }
            }
        }

        self.state = State::Finished(a);
        Poll::Ready(())
    }

    fn poll_shutdown(&mut self, context: &mut Context<'_>) -> Poll<()> {
        if matches!(self.state, State::Running { .. }) {
            task::ready!(self.poll_try_fold(context));
        }

        // During shutdown, once the state is `Finished`, we continue polling tasks but ignore
        // their results, allowing the tasks to gracefully shut down on their own.
        while !self.joinables.is_empty() {
            task::ready!(self.joinables.poll_ready(context));
            while self.joinables.try_pop_ready().is_some() {
                // Nothing to do here.
            }
        }
        Poll::Ready(())
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
        self.poll_try_fold(context)
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
        self.joinables
            .iter()
            .for_each(|joinable| joinable.add_parent(parent.clone()))
    }

    fn add_timeout(&self, timeout: Duration) {
        self.joinables
            .iter()
            .for_each(|joinable| joinable.add_timeout(timeout))
    }

    fn add_deadline(&self, deadline: Instant) {
        self.joinables
            .iter()
            .for_each(|joinable| joinable.add_deadline(deadline))
    }

    fn cancel(&self) {
        self.joinables.iter().for_each(|joinable| joinable.cancel())
    }

    async fn shutdown_with_timeout(
        &mut self,
        timeout: Duration,
    ) -> Result<<Self as Joinable>::Output, ShutdownError> {
        self.cancel();

        if time::timeout(timeout, future::poll_fn(|cx| self.poll_shutdown(cx)))
            .await
            .is_err()
        {
            drop(self.joinables.detach_all());

            return match mem::replace(&mut self.state, State::Consumed) {
                State::Running { acc, mut f } => {
                    f(acc.expect("acc"), Err(ShutdownError::JoinTimeout)).into_value()
                }
                State::Finished(acc) => acc,
                State::Consumed => panic!("TryFold has been consumed already"),
            };
        }

        self.take_result()
    }

    fn take_result(&mut self) -> Result<<Self as Joinable>::Output, ShutdownError> {
        match mem::replace(&mut self.state, State::Consumed) {
            State::Running { .. } => panic!("TryFold is still running; abort"),
            State::Finished(result) => result,
            State::Consumed => panic!("TryFold result was consumed"),
        }
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
                        "task-1"
                    }
                }),
                JoinGuard::spawn(|_| {
                    let num_joined = num_joined.clone();
                    let num_dropped = num_dropped.clone();
                    async move {
                        scopeguard::defer! {
                            num_dropped.inc();
                        }
                        future::pending::<()>().await;
                        num_joined.inc();
                        "task-2"
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
                        "task-3"
                    }
                }),
            ],
            "init",
            |_, result| ControlFlow::Break(result),
        );

        assert!(matches!(j.state, State::Running { .. }));
        assert_eq!(num_joined.get(), 0);
        assert_eq!(num_dropped.get(), 0);

        assert_eq!(
            j.shutdown_with_timeout(Duration::from_millis(10)).await,
            Ok("task-3"),
        );
        assert!(matches!(j.state, State::Consumed));
        time::sleep(Duration::from_millis(5)).await;
        assert_eq!(num_joined.get(), 2);
        assert_eq!(num_dropped.get(), 3);
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
        assert!(matches!(j.state, State::Consumed));
    }
}
