mod impls;
mod wake;

use std::future::{self, Future};
use std::pin::Pin;
use std::sync::{Arc, Mutex};
use std::task::{Context, Poll, Waker};

use crate::sync::MutexExt;

use self::impls::ReadyQueueImpl;
use self::wake::FutureWaker;

type BoxFuture<T> = Pin<Box<dyn Future<Output = T> + Send + 'static>>;

/// Polls an indefinite number of futures.
#[derive(Debug)]
pub struct ReadyQueue<T, F = BoxFuture<T>>(Arc<Mutex<ReadyQueueImpl<T, F>>>);

// `ReadyQueue::clone` is shallow, not deep.  This is the opposite of ordinary collection types.
// We keep it shallow to facilitate sharing among threads.  Besides, futures are usually not
// cloneable anyway.
//
// We cannot `derive(Clone) for `ReadyQueue` because `F` usually does not implement `Clone`.
impl<T, F> Clone for ReadyQueue<T, F> {
    fn clone(&self) -> Self {
        Self(self.0.clone())
    }
}

impl<T, F> Default for ReadyQueue<T, F> {
    fn default() -> Self {
        Self::new()
    }
}

impl<T, F> ReadyQueue<T, F> {
    pub fn new() -> Self {
        Self(Arc::new(Mutex::new(ReadyQueueImpl::new())))
    }

    pub fn close(&self) {
        let mut this = self.0.must_lock();
        this.closed = true;
        ReadyQueueImpl::wake(this)
    }

    pub fn is_closed(&self) -> bool {
        self.0.must_lock().closed
    }

    pub fn len(&self) -> usize {
        self.0.must_lock().len()
    }

    pub fn is_empty(&self) -> bool {
        self.0.must_lock().is_empty()
    }

    pub fn try_pop_ready(&self) -> Option<T> {
        self.0.must_lock().pop_ready().map(|(value, _)| value)
    }

    pub fn try_pop_ready_with_future(&self) -> Option<(T, F)> {
        self.0.must_lock().pop_ready()
    }

    /// Removes all unresolved futures from the queue.
    ///
    /// NOTE: Due to an implementation detail, if `detach_all` is called while `pop_ready` is
    /// executing, the future that is currently being polled by `pop_ready` is not included in the
    /// returned futures.
    pub fn detach_all(&self) -> Vec<F> {
        let mut this = self.0.must_lock();
        let futures = this.detach_all();
        ReadyQueueImpl::wake(this);
        futures
    }
}

impl<T> ReadyQueue<T, BoxFuture<T>> {
    pub fn push<F>(&self, future: F) -> Result<(), F>
    where
        F: Future<Output = T> + Send + 'static,
    {
        let this = self.0.must_lock();
        if this.closed {
            return Err(future);
        }
        ReadyQueueImpl::push_polling(this, Box::pin(future));
        Ok(())
    }
}

impl<T, F> ReadyQueue<T, F>
where
    F: Future<Output = T> + Send + Unpin + 'static,
    T: Send + 'static,
{
    /// Adds a future to the queue.
    ///
    /// It returns an error when the queue is closed.
    // We would like to name this method `push`, but Rust specialization seems to apply only to
    // trait implementations for now.
    pub fn push_future(&self, future: F) -> Result<(), F> {
        let this = self.0.must_lock();
        if this.closed {
            return Err(future);
        }
        ReadyQueueImpl::push_polling(this, future);
        Ok(())
    }

    /// Polls the futures and removes one of the resolved futures from the queue.
    ///
    /// It returns `None` when the queue is closed and empty.
    ///
    /// NOTE: You should *not* call `pop_ready` from multiple tasks because `ReadyQueue` keeps only
    /// one waker.  As a result, only one task will be awakened, and the rest of the tasks will
    /// sleep forever.
    // TODO: This method serves two purposes: polling the futures and removing a resolved future
    // from the queue.  Consider splitting this method into two separate ones.
    pub async fn pop_ready(&self) -> Option<T> {
        future::poll_fn(|context| self.poll_pop_ready_with_future(context))
            .await
            .map(|(value, _)| value)
    }

    /// Similar to `pop_ready`, but also returns the resolved future.
    pub async fn pop_ready_with_future(&self) -> Option<(T, F)> {
        future::poll_fn(|context| self.poll_pop_ready_with_future(context)).await
    }

    fn poll_pop_ready_with_future(&self, context: &mut Context<'_>) -> Poll<Option<(T, F)>> {
        let mut this = self.0.must_lock();
        let mut should_yield = false;
        while let Some((id, mut future)) = this.move_to_current() {
            let waker = Waker::from(Arc::new(FutureWaker::new(Arc::downgrade(&self.0), id)));
            let mut future_context = Context::from_waker(&waker);

            drop(this);
            let poll = Pin::new(&mut future).poll(&mut future_context);
            this = self.0.must_lock();

            match poll {
                Poll::Ready(value) => this.move_to_ready(id, value, future),
                Poll::Pending => {
                    if let Err((id, future)) = this.move_to_pending(id, future) {
                        // `poll` returns `Pending` but also calls `wake`, signaling that we have
                        // depleted our cooperative [budget] and should yield.
                        //
                        // [budget]: https://docs.rs/tokio/latest/tokio/task/index.html#cooperative-scheduling
                        this.return_polling(id, future);
                        should_yield = true;
                        break;
                    }
                }
            }
        }

        let output = this.pop_ready();
        match output {
            Some(_) => Poll::Ready(output),
            None => {
                if this.closed && this.is_empty() {
                    Poll::Ready(None)
                } else {
                    if should_yield {
                        context.waker().wake_by_ref();
                    } else {
                        this.update_waker(context);
                    }
                    Poll::Pending
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use std::future;
    use std::time::Duration;

    use tokio::time;

    use super::{impls::test_harness::MockWaker, *};

    fn assert_queue<T, F>(queue: &ReadyQueue<T, F>, is_closed: bool, len: usize) {
        assert_eq!(queue.is_closed(), is_closed);
        assert_eq!(queue.len(), len);
        assert_eq!(queue.is_empty(), len == 0);
    }

    #[tokio::test]
    async fn ready_queue() {
        // We cannot use `assert_matches!` because async blocks do not implement `Debug`.

        let queue = ReadyQueue::new();
        assert_queue(&queue, false, 0);

        assert!(matches!(queue.push(async { 0usize }), Ok(())));
        assert_queue(&queue, false, 1);

        assert!(matches!(queue.push(async { 1usize }), Ok(())));
        assert_queue(&queue, false, 2);

        queue.close();
        assert_queue(&queue, true, 2);

        assert!(matches!(queue.push(async { 2usize }), Err(_)));
        assert_queue(&queue, true, 2);

        assert_eq!(queue.pop_ready().await, Some(0usize));
        assert_queue(&queue, true, 1);

        assert_eq!(queue.pop_ready().await, Some(1usize));
        assert_queue(&queue, true, 0);

        for _ in 0..3 {
            assert_eq!(queue.pop_ready().await, None);
            assert_queue(&queue, true, 0);
        }
    }

    #[test]
    fn poll_pop_ready_with_future() {
        let mock_waker = Arc::new(MockWaker::new());
        let waker = Waker::from(mock_waker.clone());
        let mut context = Context::from_waker(&waker);

        let queue = ReadyQueue::new();
        for _ in 0..10 {
            assert!(matches!(queue.push(future::pending::<()>()), Ok(())));
        }
        assert_queue(&queue, false, 10);
        assert_eq!(mock_waker.num_calls(), 0);

        for _ in 1..=3 {
            assert!(matches!(
                queue.poll_pop_ready_with_future(&mut context),
                Poll::Pending,
            ));
            assert_queue(&queue, false, 10);
            assert_eq!(mock_waker.num_calls(), 0);
        }
    }

    #[test]
    fn poll_pop_ready_with_future_yield() {
        struct Yield;

        impl Future for Yield {
            type Output = ();

            fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
                context.waker().wake_by_ref();
                Poll::Pending
            }
        }

        let mock_waker = Arc::new(MockWaker::new());
        let waker = Waker::from(mock_waker.clone());
        let mut context = Context::from_waker(&waker);

        let queue = ReadyQueue::new();
        for _ in 0..10 {
            assert!(matches!(queue.push(Yield), Ok(())));
        }
        assert_queue(&queue, false, 10);
        assert_eq!(mock_waker.num_calls(), 0);

        for i in 1..=3 {
            assert!(matches!(
                queue.poll_pop_ready_with_future(&mut context),
                Poll::Pending,
            ));
            assert_queue(&queue, false, 10);
            assert_eq!(mock_waker.num_calls(), i);
        }
    }

    #[tokio::test]
    async fn detach_all() {
        let queue = ReadyQueue::new();
        assert_queue(&queue, false, 0);

        assert!(matches!(queue.push(future::pending()), Ok(())));
        assert!(matches!(queue.push(future::pending()), Ok(())));
        assert!(matches!(queue.push(future::pending()), Ok(())));
        assert!(matches!(queue.push(async { 0usize }), Ok(())));
        assert!(matches!(
            queue.push_future(Box::pin(async { 1usize })),
            Ok(()),
        ));
        queue.close();
        assert_queue(&queue, true, 5);

        assert_eq!(queue.pop_ready().await, Some(0usize));
        assert_queue(&queue, true, 4);

        assert_eq!(queue.detach_all().len(), 3);
        assert_queue(&queue, true, 1);

        assert_eq!(queue.pop_ready().await, Some(1usize));
        assert_queue(&queue, true, 0);
    }

    #[tokio::test]
    async fn close_unblock_pop_ready() {
        let queue = ReadyQueue::<()>::new();
        assert_queue(&queue, false, 0);

        let pop_ready_task = {
            let queue = queue.clone();
            tokio::spawn(async move { queue.pop_ready().await })
        };
        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(pop_ready_task.is_finished(), false);

        queue.close();
        assert_queue(&queue, true, 0);

        assert!(matches!(pop_ready_task.await, Ok(None)));
    }

    #[tokio::test]
    async fn detach_all_unblock_pop_ready() {
        let queue = ReadyQueue::<()>::new();
        assert!(matches!(queue.push(future::pending()), Ok(())));
        queue.close();
        assert_queue(&queue, true, 1);

        let pop_ready_task = {
            let queue = queue.clone();
            tokio::spawn(async move { queue.pop_ready().await })
        };
        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(pop_ready_task.is_finished(), false);

        assert_eq!(queue.detach_all().len(), 1);
        assert_queue(&queue, true, 0);

        assert!(matches!(pop_ready_task.await, Ok(None)));
    }
}
