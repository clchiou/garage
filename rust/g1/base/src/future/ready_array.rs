use std::collections::VecDeque;
use std::future::{self, Future};
use std::pin::Pin;
use std::sync::{Arc, Mutex};
use std::task::{Context, Poll, Wake, Waker};

use crate::sync::MutexExt;

/// Polls an array of futures.
///
/// NOTE: `ReadyArray` does not preserve the order of the futures.
#[derive(Debug)]
pub struct ReadyArray<Fut, const N: usize>
where
    Fut: Future + Unpin,
{
    // `futures` is split into `0..num_pending` and `num_pending..N`.
    futures: [Fut; N],
    ready: VecDeque<Fut::Output>,
    num_pending: usize,
}

#[derive(Clone, Debug)]
struct OnceWaker(Arc<Mutex<Option<Waker>>>);

impl<Fut, const N: usize> ReadyArray<Fut, N>
where
    Fut: Future + Unpin,
{
    pub fn new(futures: [Fut; N]) -> Self {
        Self {
            futures,
            ready: VecDeque::new(),
            num_pending: N,
        }
    }

    pub fn iter(&self) -> impl Iterator<Item = &Fut> {
        self.futures.iter()
    }

    pub fn iter_mut(&mut self) -> impl Iterator<Item = &mut Fut> {
        self.futures.iter_mut()
    }

    pub fn into_futures(self) -> [Fut; N] {
        self.futures
    }

    pub fn is_ready(&self) -> bool {
        self.num_pending == 0 || !self.ready.is_empty()
    }

    pub fn try_pop_ready(&mut self) -> Option<Fut::Output> {
        self.ready.pop_front()
    }

    pub async fn ready(&mut self) {
        future::poll_fn(|context| self.poll_futures(context)).await
    }

    pub async fn pop_ready(&mut self) -> Option<Fut::Output> {
        self.ready().await;
        self.ready.pop_front()
    }

    fn poll_futures(&mut self, context: &mut Context<'_>) -> Poll<()> {
        if self.num_pending == 0 {
            return Poll::Ready(());
        }

        let once_waker = OnceWaker::new(context.waker().clone());
        let waker = Waker::from(Arc::new(once_waker.clone()));
        let mut future_context = Context::from_waker(&waker);
        let mut i = 0;
        while i < self.num_pending {
            match Pin::new(&mut self.futures[i]).poll(&mut future_context) {
                Poll::Ready(output) => {
                    self.num_pending -= 1;
                    self.futures.swap(i, self.num_pending);
                    self.ready.push_back(output);
                }
                Poll::Pending => {
                    if once_waker.0.must_lock().is_none() {
                        // `poll` returns `Pending` but also calls `wake`, signaling that we have
                        // depleted our cooperative [budget] and should yield.
                        //
                        // [budget]: https://docs.rs/tokio/latest/tokio/task/index.html#cooperative-scheduling
                        return Poll::Pending;
                    }
                    i += 1;
                }
            }
        }

        if self.is_ready() {
            Poll::Ready(())
        } else {
            Poll::Pending
        }
    }
}

impl OnceWaker {
    fn new(waker: Waker) -> Self {
        Self(Arc::new(Mutex::new(Some(waker))))
    }
}

impl Wake for OnceWaker {
    fn wake(self: Arc<Self>) {
        Self::wake_by_ref(&self);
    }

    fn wake_by_ref(self: &Arc<Self>) {
        if let Some(waker) = self.0.must_lock().take() {
            waker.wake();
        }
    }
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use tokio::time;

    use super::*;

    type BoxFuture<T> = Pin<Box<dyn Future<Output = T>>>;

    #[tokio::test]
    async fn empty() {
        let mut array = ReadyArray::<BoxFuture<()>, 0>::new([]);
        assert_eq!(array.is_ready(), true);
        assert_eq!(array.num_pending, 0);

        for _ in 0..3 {
            assert_eq!(array.ready().await, ());
            assert_eq!(array.pop_ready().await, None);
            assert_eq!(array.is_ready(), true);
            assert_eq!(array.num_pending, 0);
        }
    }

    #[tokio::test]
    async fn ready() {
        let mut array = ReadyArray::<BoxFuture<u8>, 3>::new([
            Box::pin(async { 100 }),
            Box::pin(async { 101 }),
            Box::pin(async { 102 }),
        ]);
        assert_eq!(array.is_ready(), false);
        assert_eq!(array.num_pending, 3);

        for _ in 0..3 {
            assert_eq!(array.ready().await, ());
            assert_eq!(array.is_ready(), true);
            assert_eq!(array.num_pending, 0);
        }
    }

    #[tokio::test]
    async fn ready_pending() {
        let mut array = ReadyArray::<BoxFuture<u8>, 2>::new([
            Box::pin(future::pending()),
            Box::pin(async { 100 }),
        ]);
        assert_eq!(array.is_ready(), false);
        assert_eq!(array.num_pending, 2);

        for _ in 0..3 {
            assert_eq!(array.ready().await, ());
            assert_eq!(array.is_ready(), true);
            assert_eq!(array.num_pending, 1);
        }

        assert_eq!(array.try_pop_ready(), Some(100));
        assert_eq!(array.is_ready(), false);

        // TODO: Can we write this test without using `time::sleep`?
        tokio::select! {
            () = time::sleep(Duration::from_millis(10)) => {}
            () = array.ready() => std::panic!(),
        }
    }

    #[tokio::test]
    async fn pop_ready() {
        let mut array = ReadyArray::<BoxFuture<u8>, 3>::new([
            Box::pin(async { 100 }),
            Box::pin(async { 101 }),
            Box::pin(async { 102 }),
        ]);

        let mut outputs = [
            array.pop_ready().await,
            array.pop_ready().await,
            array.pop_ready().await,
        ];
        outputs.sort();
        assert_eq!(outputs, [Some(100), Some(101), Some(102)]);
        assert_eq!(array.num_pending, 0);

        for _ in 0..3 {
            assert_eq!(array.pop_ready().await, None);
            assert_eq!(array.num_pending, 0);
        }
    }

    #[tokio::test]
    async fn pop_ready_pending() {
        let mut array = ReadyArray::<BoxFuture<u8>, 2>::new([
            Box::pin(future::pending()),
            Box::pin(async { 100 }),
        ]);

        assert_eq!(array.pop_ready().await, Some(100));
        assert_eq!(array.is_ready(), false);
        assert_eq!(array.num_pending, 1);

        // TODO: Can we write this test without using `time::sleep`?
        tokio::select! {
            () = time::sleep(Duration::from_millis(10)) => {}
            _ = array.pop_ready() => std::panic!(),
        }
    }
}
