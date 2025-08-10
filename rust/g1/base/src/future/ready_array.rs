use std::future::{self, Future};
use std::mem::{self, MaybeUninit};
use std::pin::Pin;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::task::{Context, Poll, Wake, Waker};

use crate::collections::{Array, array};

/// Polls an array of futures.
///
/// NOTE: `ReadyArray` does not preserve the order of the futures.
#[derive(Debug)]
pub struct ReadyArray<Fut, const N: usize>
where
    Fut: Future + Unpin,
{
    // `futures` is split into the ranges `0..num_pending` and `num_pending..`.
    //
    // NOTE: It is important to maintain that once a future is moved into the "ready" group, its
    // index remains unchanged, as it also serves as the index in `values` where its output is
    // stored.
    futures: Array<Fut, N>,
    values: [MaybeUninit<Fut::Output>; N],
    num_pending: usize,
}

impl<Fut, const N: usize> Drop for ReadyArray<Fut, N>
where
    Fut: Future + Unpin,
{
    fn drop(&mut self) {
        self.drop_values_in_place();
    }
}

struct TrackedWaker {
    waker: Waker,
    flag: AtomicBool,
}

impl<Fut, const N: usize> ReadyArray<Fut, N>
where
    Fut: Future + Unpin,
{
    pub fn new(futures: [Fut; N]) -> Self {
        Self {
            futures: futures.into(),
            values: [const { MaybeUninit::uninit() }; N],
            num_pending: N,
        }
    }

    fn drop_values_in_place(&mut self) {
        let values = &mut self.values[self.num_pending..self.futures.len()];
        unsafe { values.assume_init_drop() };
    }

    fn num_ready(&self) -> usize {
        self.futures.len() - self.num_pending
    }

    pub fn detach_all(&mut self) -> Array<Fut, N> {
        self.drop_values_in_place();
        let mut futures = mem::take(&mut self.futures);
        let num_pending = mem::take(&mut self.num_pending);
        futures.truncate(num_pending);
        futures
    }

    pub fn iter(&self) -> impl Iterator<Item = &Fut> {
        self.futures.iter().take(self.num_pending)
    }

    pub fn iter_mut(&mut self) -> impl Iterator<Item = &mut Fut> {
        self.futures.iter_mut().take(self.num_pending)
    }

    pub fn is_ready(&self) -> bool {
        self.num_ready() > 0 || self.num_pending == 0
    }

    pub fn try_pop_ready(&mut self) -> Option<Fut::Output> {
        self.try_pop_ready_with_future().map(|(value, _)| value)
    }

    pub fn try_pop_ready_with_future(&mut self) -> Option<(Fut::Output, Fut)> {
        (self.num_ready() > 0).then(|| {
            let fut = self.futures.pop().expect("futures");
            let i = self.futures.len();
            (unsafe { self.values[i].assume_init_read() }, fut)
        })
    }

    pub async fn ready(&mut self) {
        future::poll_fn(|context| self.poll_futures(context)).await
    }

    pub async fn pop_ready(&mut self) -> Option<Fut::Output> {
        self.pop_ready_with_future().await.map(|(value, _)| value)
    }

    pub async fn pop_ready_with_future(&mut self) -> Option<(Fut::Output, Fut)> {
        self.ready().await;
        self.try_pop_ready_with_future()
    }

    fn poll_futures(&mut self, context: &mut Context<'_>) -> Poll<()> {
        if self.num_pending == 0 {
            return Poll::Ready(());
        }

        let tracked_waker = Arc::new(TrackedWaker::new(context.waker().clone()));
        let waker = Waker::from(tracked_waker.clone());
        let mut future_context = Context::from_waker(&waker);
        let mut i = 0;
        while i < self.num_pending {
            match Pin::new(&mut self.futures[i]).poll(&mut future_context) {
                Poll::Ready(output) => {
                    self.num_pending -= 1;
                    self.futures.swap(i, self.num_pending);
                    self.values[self.num_pending].write(output);
                }
                Poll::Pending => {
                    // A future may yield voluntarily -- for example, when it is compute-bound.
                    // (In such cases, we should move it to the end of the pending queue.)
                    // However, we are not specifically targeting any runtime (e.g., `tokio`) at
                    // this point, so we can only make a best-effort attempt to detect a yield by
                    // checking whether `wake` has been called, as `tokio` sometimes does this when
                    // a task's cooperative [budget] has been depleted.
                    //
                    // [budget]: https://docs.rs/tokio/latest/tokio/task/coop/index.html#cooperative-scheduling
                    if tracked_waker.is_called() {
                        self.futures[i..self.num_pending].rotate_left(1);
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

pub type IntoIter<Fut: Future + Unpin, const N: usize> = array::IntoIter<Fut, N>;

impl<Fut, const N: usize> IntoIterator for ReadyArray<Fut, N>
where
    Fut: Future + Unpin,
{
    type Item = Fut;
    type IntoIter = IntoIter<Fut, N>;

    fn into_iter(mut self) -> Self::IntoIter {
        self.detach_all().into_iter()
    }
}

impl TrackedWaker {
    fn new(waker: Waker) -> Self {
        Self {
            waker,
            flag: AtomicBool::new(false),
        }
    }

    fn is_called(&self) -> bool {
        // TODO: Should we use `Ordering::Relaxed` instead?
        self.flag.load(Ordering::SeqCst)
    }
}

impl Wake for TrackedWaker {
    fn wake(self: Arc<Self>) {
        self.wake_by_ref();
    }

    fn wake_by_ref(self: &Arc<Self>) {
        self.waker.wake_by_ref();
        // TODO: Should we use `Ordering::Relaxed` instead?
        self.flag.store(true, Ordering::SeqCst)
    }
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::AtomicUsize;
    use std::time::Duration;

    use tokio::time;

    use super::*;

    type BoxFuture<T> = Pin<Box<dyn Future<Output = T>>>;

    struct Mock(i8);

    impl Future for Mock {
        type Output = i8;

        fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
            let x = self.as_ref().0;
            if x > 0 {
                Poll::Ready(x)
            } else {
                if x == 0 {
                    context.waker().wake_by_ref();
                }
                Poll::Pending
            }
        }
    }

    impl<const N: usize> ReadyArray<Mock, N> {
        fn assert_mocks(&self, expect: &[i8]) {
            assert_mocks(&self.futures, expect);
        }
    }

    fn assert_mocks<const N: usize>(array: &Array<Mock, N>, expect: &[i8]) {
        let actual: Vec<_> = array.iter().map(|x| x.0).collect();
        assert_eq!(actual, expect);
    }

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
    async fn drop_values_in_place() {
        struct Scoped<'a>(&'a AtomicUsize);

        impl Drop for Scoped<'_> {
            fn drop(&mut self) {
                self.0.fetch_add(1, Ordering::SeqCst);
            }
        }

        {
            let num_dropped = AtomicUsize::new(0);
            let mut array = ReadyArray::new([
                future::ready(Scoped(&num_dropped)),
                future::ready(Scoped(&num_dropped)),
                future::ready(Scoped(&num_dropped)),
            ]);
            assert_eq!(num_dropped.load(Ordering::SeqCst), 0);
            assert_eq!(array.num_pending, 3);

            array.ready().await;
            assert_eq!(num_dropped.load(Ordering::SeqCst), 0);
            assert_eq!(array.num_pending, 0);

            drop(array);
            assert_eq!(num_dropped.load(Ordering::SeqCst), 3);
        }

        {
            let num_dropped = AtomicUsize::new(0);
            let mut array = ReadyArray::new([
                future::ready(Scoped(&num_dropped)),
                future::ready(Scoped(&num_dropped)),
                future::ready(Scoped(&num_dropped)),
            ]);
            assert_eq!(num_dropped.load(Ordering::SeqCst), 0);
            assert_eq!(array.num_pending, 3);

            let scoped = array.pop_ready().await.unwrap();
            assert_eq!(num_dropped.load(Ordering::SeqCst), 0);
            assert_eq!(array.num_pending, 0);

            drop(array);
            assert_eq!(num_dropped.load(Ordering::SeqCst), 2);

            drop(scoped);
            assert_eq!(num_dropped.load(Ordering::SeqCst), 3);
        }

        {
            let num_dropped = AtomicUsize::new(0);
            let mut array = ReadyArray::new([
                future::ready(Scoped(&num_dropped)),
                future::ready(Scoped(&num_dropped)),
                future::ready(Scoped(&num_dropped)),
            ]);
            assert_eq!(num_dropped.load(Ordering::SeqCst), 0);
            assert_eq!(array.num_pending, 3);

            array.ready().await;
            assert_eq!(num_dropped.load(Ordering::SeqCst), 0);
            assert_eq!(array.num_pending, 0);

            let futures = array.detach_all();
            assert_eq!(num_dropped.load(Ordering::SeqCst), 3);
            assert!(futures.is_empty());
        }
    }

    #[tokio::test]
    async fn detach_all() {
        fn assert_iter<const N: usize>(array: &mut ReadyArray<Mock, N>, expect: &[i8]) {
            let actual: Vec<_> = array.iter().map(|x| x.0).collect();
            assert_eq!(actual, expect);

            let actual: Vec<_> = array.iter_mut().map(|x| x.0).collect();
            assert_eq!(actual, expect);
        }

        let mut array = ReadyArray::<Mock, 4>::new([Mock(-2), Mock(3), Mock(-1), Mock(4)]);
        array.assert_mocks(&[-2, 3, -1, 4]);
        assert_iter(&mut array, &[-2, 3, -1, 4]);
        assert_eq!(array.num_pending, 4);

        array.ready().await;
        array.assert_mocks(&[-2, -1, 4, 3]);
        assert_iter(&mut array, &[-2, -1]);
        assert_eq!(array.num_pending, 2);

        assert_mocks(&array.detach_all(), &[-2, -1]);
        array.assert_mocks(&[]);
        assert_iter(&mut array, &[]);
        assert_eq!(array.num_pending, 0);
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

    #[test]
    fn test_yield() {
        let waker = Waker::noop();
        let mut context = Context::from_waker(&waker);

        let mut array = ReadyArray::<Mock, 3>::new([Mock(0), Mock(1), Mock(2)]);
        array.assert_mocks(&[0, 1, 2]);
        assert_eq!(array.num_pending, 3);

        assert_eq!(array.poll_futures(&mut context), Poll::Pending);
        array.assert_mocks(&[1, 2, 0]);
        assert_eq!(array.num_pending, 3);

        assert_eq!(array.poll_futures(&mut context), Poll::Pending);
        array.assert_mocks(&[2, 0, 1]);
        assert_eq!(array.num_pending, 2);

        for _ in 0..3 {
            assert_eq!(array.poll_futures(&mut context), Poll::Pending);
            array.assert_mocks(&[0, 2, 1]);
            assert_eq!(array.num_pending, 1);
        }

        let mut array =
            ReadyArray::<Mock, 6>::new([Mock(-1), Mock(-2), Mock(0), Mock(0), Mock(3), Mock(4)]);
        array.assert_mocks(&[-1, -2, 0, 0, 3, 4]);
        assert_eq!(array.num_pending, 6);

        assert_eq!(array.poll_futures(&mut context), Poll::Pending);
        array.assert_mocks(&[-1, -2, 0, 3, 4, 0]);
        assert_eq!(array.num_pending, 6);

        assert_eq!(array.poll_futures(&mut context), Poll::Pending);
        array.assert_mocks(&[-1, -2, 3, 4, 0, 0]);
        assert_eq!(array.num_pending, 6);

        assert_eq!(array.poll_futures(&mut context), Poll::Pending);
        array.assert_mocks(&[-1, -2, 4, 0, 0, 3]);
        assert_eq!(array.num_pending, 5);

        for _ in 0..3 {
            assert_eq!(array.poll_futures(&mut context), Poll::Pending);
            array.assert_mocks(&[-1, -2, 0, 0, 4, 3]);
            assert_eq!(array.num_pending, 4);
        }
    }
}
