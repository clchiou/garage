mod poll;
mod queue;
mod wake;

use std::future::Future;
use std::pin::Pin;
use std::sync::{Arc, Mutex};

use crate::sync::MutexExt;

use self::{
    poll::{PopReady, Ready},
    queue::Queue,
};

pub type BoxFuture<T> = Pin<Box<dyn Future<Output = T> + Send + 'static>>;

/// Polls an indefinite number of futures.
#[derive(Debug)]
pub struct ReadyQueue<T, Fut = BoxFuture<T>>(Arc<Mutex<Queue<T, Fut>>>);

// `ReadyQueue::clone` is shallow, not deep.  This is the opposite of ordinary collection types.
// We keep it shallow to facilitate sharing among threads.  Besides, futures are usually not
// cloneable anyway.
//
// We cannot `derive(Clone) for `ReadyQueue` because `Fut` usually does not implement `Clone`.
impl<T, Fut> Clone for ReadyQueue<T, Fut> {
    fn clone(&self) -> Self {
        Self(self.0.clone())
    }
}

impl<T, Fut> Default for ReadyQueue<T, Fut> {
    fn default() -> Self {
        Self::new()
    }
}

impl<T, Fut> ReadyQueue<T, Fut> {
    pub fn new() -> Self {
        Self(Arc::new(Mutex::new(Queue::new())))
    }

    pub fn close(&self) {
        self.0.must_lock().close()
    }

    pub fn is_closed(&self) -> bool {
        self.0.must_lock().is_closed()
    }

    pub fn len(&self) -> usize {
        self.0.must_lock().len()
    }

    pub fn is_empty(&self) -> bool {
        self.0.must_lock().is_empty()
    }

    pub fn is_ready(&self) -> bool {
        self.0.must_lock().is_ready()
    }

    pub fn try_pop_ready(&self) -> Option<T> {
        self.0.must_lock().pop_ready().map(|(value, _)| value)
    }

    pub fn try_pop_ready_with_future(&self) -> Option<(T, Fut)> {
        self.0.must_lock().pop_ready()
    }

    /// Removes all unresolved futures from the queue.
    ///
    /// NOTE: Due to an implementation detail, if `detach_all` is called while `pop_ready` is
    /// executing, the future that is currently being polled by `pop_ready` is not included in the
    /// returned futures.
    pub fn detach_all(&self) -> Vec<Fut> {
        self.0.must_lock().detach_all()
    }
}

impl<T> ReadyQueue<T, BoxFuture<T>> {
    pub fn push<Fut>(&self, future: Fut) -> Result<(), Fut>
    where
        Fut: Future<Output = T> + Send + 'static,
    {
        let mut this = self.0.must_lock();
        if this.is_closed() {
            return Err(future);
        }
        this.push_polling(Box::pin(future));
        Ok(())
    }
}

impl<T, Fut> ReadyQueue<T, Fut>
where
    Fut: Future<Output = T> + Send + Unpin + 'static,
    T: Send + 'static,
{
    /// Adds a future to the queue.
    ///
    /// It returns an error when the queue is closed.
    // We would like to name this method `push`, but Rust specialization seems to apply only to
    // trait implementations for now.
    pub fn push_future(&self, future: Fut) -> Result<(), Fut> {
        let mut this = self.0.must_lock();
        if this.is_closed() {
            return Err(future);
        }
        this.push_polling(future);
        Ok(())
    }

    /// Similar to `pop_ready`, but does not remove a future from the queue.
    pub fn ready(&self) -> impl Future<Output = ()> + use<T, Fut> {
        Ready::new(self.0.clone())
    }

    /// Polls the futures and removes one of the resolved futures from the queue.
    ///
    /// It returns `None` when the queue is closed and empty.
    pub fn pop_ready(&self) -> impl Future<Output = Option<T>> + use<T, Fut> {
        let pop_ready = self.pop_ready_with_future();
        async move { pop_ready.await.map(|(value, _)| value) }
    }

    /// Similar to `pop_ready`, but also returns the resolved future.
    pub fn pop_ready_with_future(&self) -> impl Future<Output = Option<(T, Fut)>> + use<T, Fut> {
        PopReady::new(self.0.clone())
    }
}

#[cfg(test)]
pub(crate) mod test_harness {
    use std::future::Future;
    use std::marker::PhantomData;
    use std::pin::Pin;
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };
    use std::task::{Context, Poll, Wake, Waker};

    pub(crate) struct MockContext {
        pub(crate) mock_waker: Arc<MockWaker>,
        pub(crate) waker: Waker,
    }

    impl MockContext {
        pub(crate) fn new() -> Self {
            let mock_waker = Arc::new(MockWaker::new());
            Self {
                mock_waker: mock_waker.clone(),
                waker: Waker::from(mock_waker),
            }
        }

        pub(crate) fn context(&self) -> Context {
            Context::from_waker(&self.waker)
        }
    }

    pub(crate) struct MockWaker(AtomicUsize);

    impl MockWaker {
        pub(crate) fn new() -> Self {
            Self(AtomicUsize::new(0))
        }

        pub(crate) fn get(&self) -> usize {
            self.0.load(Ordering::SeqCst)
        }

        pub(crate) fn reset(&self) {
            self.0.store(0, Ordering::SeqCst);
        }
    }

    impl Wake for MockWaker {
        fn wake(self: Arc<Self>) {
            Self::wake_by_ref(&self);
        }

        fn wake_by_ref(self: &Arc<Self>) {
            self.0.fetch_add(1, Ordering::SeqCst);
        }
    }

    pub(crate) struct Yield<T>(PhantomData<T>);

    impl<T> Yield<T> {
        pub(crate) fn new() -> Self {
            Self(PhantomData)
        }
    }

    impl<T> Future for Yield<T> {
        type Output = T;

        fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
            context.waker().wake_by_ref();
            Poll::Pending
        }
    }
}

#[cfg(test)]
mod tests {
    use std::future;
    use std::time::Duration;

    use tokio::time;

    use super::*;

    #[tokio::test]
    async fn ready_queue() {
        fn assert<T, F>(queue: &ReadyQueue<T, F>, is_closed: bool, len: usize, is_ready: bool) {
            assert_eq!(queue.is_closed(), is_closed);
            assert_eq!(queue.len(), len);
            assert_eq!(queue.is_empty(), len == 0);
            assert_eq!(queue.is_ready(), is_ready);
        }

        let queue = ReadyQueue::new();
        assert(&queue, false, 0, false);

        assert!(matches!(queue.push(future::ready(101)), Ok(())));
        assert(&queue, false, 1, false);

        assert!(matches!(
            queue.push_future(Box::pin(future::ready(102))),
            Ok(()),
        ));
        assert(&queue, false, 2, false);

        queue.close();
        assert(&queue, true, 2, false);

        assert!(matches!(queue.push(future::ready(103)), Err(_)));
        assert(&queue, true, 2, false);
        assert!(matches!(
            queue.push_future(Box::pin(future::ready(104))),
            Err(_),
        ));
        assert(&queue, true, 2, false);

        assert_eq!(queue.pop_ready().await, Some(101));
        assert(&queue, true, 1, true);

        assert_eq!(queue.pop_ready().await, Some(102));
        assert(&queue, true, 0, true);

        for _ in 0..3 {
            assert_eq!(queue.pop_ready().await, None);
            assert(&queue, true, 0, true);
        }
    }

    #[tokio::test]
    async fn detach_all() {
        let queue = ReadyQueue::new();
        assert!(matches!(queue.push(future::pending()), Ok(())));
        assert!(matches!(queue.push(future::ready(101)), Ok(())));
        assert_eq!(queue.detach_all().len(), 2);

        let queue = ReadyQueue::new();
        assert!(matches!(queue.push(future::pending()), Ok(())));
        assert!(matches!(queue.push(future::ready(101)), Ok(())));
        assert_eq!(queue.ready().await, ());
        assert_eq!(queue.detach_all().len(), 1);
    }

    #[tokio::test]
    async fn multitasking() {
        let queue = ReadyQueue::new();

        let ready_tasks = [
            tokio::spawn(queue.ready()),
            tokio::spawn(queue.ready()),
            tokio::spawn(queue.ready()),
        ];
        let pop_ready_tasks = [
            tokio::spawn(queue.pop_ready()),
            tokio::spawn(queue.pop_ready()),
            tokio::spawn(queue.pop_ready()),
        ];
        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        for task in &ready_tasks {
            assert_eq!(task.is_finished(), false);
        }
        for task in &pop_ready_tasks {
            assert_eq!(task.is_finished(), false);
        }

        assert!(matches!(queue.push(future::ready(102)), Ok(())));
        assert!(matches!(queue.push(future::ready(101)), Ok(())));
        assert!(matches!(queue.push(future::ready(103)), Ok(())));

        for task in ready_tasks {
            assert!(matches!(task.await, Ok(())));
        }
        let mut outputs = Vec::new();
        for task in pop_ready_tasks {
            outputs.push(task.await.unwrap().unwrap());
        }
        outputs.sort();
        assert_eq!(outputs, [101, 102, 103]);
    }

    #[tokio::test]
    async fn multitasking_close() {
        let queue = ReadyQueue::<()>::new();

        let ready_tasks = [
            tokio::spawn(queue.ready()),
            tokio::spawn(queue.ready()),
            tokio::spawn(queue.ready()),
        ];
        let pop_ready_tasks = [
            tokio::spawn(queue.pop_ready()),
            tokio::spawn(queue.pop_ready()),
            tokio::spawn(queue.pop_ready()),
        ];
        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        for task in &ready_tasks {
            assert_eq!(task.is_finished(), false);
        }
        for task in &pop_ready_tasks {
            assert_eq!(task.is_finished(), false);
        }

        queue.close();

        for task in ready_tasks {
            assert!(matches!(task.await, Ok(())));
        }
        for task in pop_ready_tasks {
            assert!(matches!(task.await, Ok(None)));
        }
    }
}
