use std::future::Future;
use std::marker::PhantomData;
use std::pin::Pin;
use std::sync::{Arc, Mutex};
use std::task::{Context, Poll, Waker};

use crate::{collections::vec_list::Cursor, sync::MutexExt};

use super::{
    queue::{Queue, Wakers},
    wake::FutureWaker,
};

pub(super) type Ready<T, Fut> = Poller<T, Fut, ReadyFunc>;
pub(super) type PopReady<T, Fut> = Poller<T, Fut, PopReadyFunc>;

#[derive(Debug)]
pub(super) struct Poller<T, Fut, Func>
where
    Func: PollFunc<T, Fut>,
{
    queue: Arc<Mutex<Queue<T, Fut>>>,
    waker: Option<Cursor>,
    _func: PhantomData<Func>,
}

#[derive(Debug)]
pub(super) struct ReadyFunc;

#[derive(Debug)]
pub(super) struct PopReadyFunc;

pub(super) trait PollFunc<T, Fut> {
    type Output;

    fn wakers(queue: &mut Queue<T, Fut>) -> &mut Wakers;

    fn output(queue: &mut Queue<T, Fut>) -> Poll<Self::Output>;
}

impl<T, Fut, Func> Poller<T, Fut, Func>
where
    Func: PollFunc<T, Fut>,
{
    pub(super) fn new(queue: Arc<Mutex<Queue<T, Fut>>>) -> Self {
        Self {
            queue,
            waker: None,
            _func: PhantomData,
        }
    }
}

impl<T, Fut, Func> Future for Poller<T, Fut, Func>
where
    Fut: Future<Output = T> + Send + Unpin + 'static,
    T: Send + 'static,
    Func: PollFunc<T, Fut> + Unpin,
{
    type Output = Func::Output;

    fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
        let this = self.get_mut();
        let mut queue = this.queue.must_lock();

        if this.waker.is_none() {
            this.waker = Some(Func::wakers(&mut queue).reserve());
        }

        while let Some((id, mut future)) = queue.next_polling() {
            let future_waker = FutureWaker::new(Arc::downgrade(&this.queue), id);
            let future_waker = Waker::from(Arc::new(future_waker));
            let mut future_context = Context::from_waker(&future_waker);

            Mutex::unlock(queue);
            let poll_output = Pin::new(&mut future).poll(&mut future_context);
            queue = this.queue.must_lock();

            match poll_output {
                Poll::Ready(value) => queue.push_ready(id, value, future),
                Poll::Pending => {
                    if let Err(future) = queue.push_pending(id, future) {
                        // `poll` returns `Pending` but also calls `wake`, signaling that we have
                        // depleted our cooperative [budget] and should yield.
                        //
                        // [budget]: https://docs.rs/tokio/latest/tokio/task/index.html#cooperative-scheduling
                        queue.resume_polling_after_yield(future);
                        context.waker().wake_by_ref();
                        return Poll::Pending;
                    }
                }
            }
        }

        let poll_output = Func::output(&mut queue);
        if poll_output.is_pending() {
            Func::wakers(&mut queue).update(this.waker.unwrap(), context);
        }
        poll_output
    }
}

impl<T, Fut, Func> Drop for Poller<T, Fut, Func>
where
    Func: PollFunc<T, Fut>,
{
    fn drop(&mut self) {
        if let Some(waker) = self.waker {
            let mut queue = self.queue.must_lock();
            Func::wakers(&mut queue).remove(waker);
            // `Poller::poll` has been called, but there are still futures that need to be polled.
            // This could be due to yielding or some pathological cases.  If it is the latter, we
            // need to ensure that a polling task is always running.  This might result in
            // over-waking tasks, but it is still more efficient than waking up all tasks all the
            // time.
            if queue.has_polling() {
                queue.wake_one();
            }
        }
    }
}

impl<T, Fut> PollFunc<T, Fut> for ReadyFunc {
    type Output = ();

    fn wakers(queue: &mut Queue<T, Fut>) -> &mut Wakers {
        &mut queue.ready_wakers
    }

    fn output(queue: &mut Queue<T, Fut>) -> Poll<Self::Output> {
        if queue.is_ready() {
            Poll::Ready(())
        } else {
            Poll::Pending
        }
    }
}

impl<T, Fut> PollFunc<T, Fut> for PopReadyFunc {
    type Output = Option<(T, Fut)>;

    fn wakers(queue: &mut Queue<T, Fut>) -> &mut Wakers {
        &mut queue.pop_ready_wakers
    }

    fn output(queue: &mut Queue<T, Fut>) -> Poll<Self::Output> {
        match queue.pop_ready() {
            output @ Some(_) => Poll::Ready(output),
            None => {
                if queue.is_closed() && queue.is_empty() {
                    Poll::Ready(None)
                } else {
                    Poll::Pending
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use std::future;

    use super::{
        super::{
            test_harness::{MockContext, Yield},
            BoxFuture,
        },
        *,
    };

    struct Test {
        queue: Arc<Mutex<Queue<usize, BoxFuture<usize>>>>,

        mock: MockContext,

        mock_ready: MockContext,
        mock_ready_cursors: [Cursor; 5],

        mock_pop_ready: MockContext,
        mock_pop_ready_cursors: [Cursor; 5],
    }

    impl Test {
        fn new<const N: usize>(futures: [BoxFuture<usize>; N]) -> Self {
            let queue = Arc::new(Mutex::new(Queue::new()));
            let mock = MockContext::new();
            let mock_ready = MockContext::new();
            let mock_ready_cursors;
            let mock_pop_ready = MockContext::new();
            let mock_pop_ready_cursors;
            {
                let mut queue = queue.must_lock();
                for future in futures {
                    queue.push_polling(future);
                }
                mock_ready_cursors = [
                    queue.ready_wakers.push_mock(&mock_ready),
                    queue.ready_wakers.push_mock(&mock_ready),
                    queue.ready_wakers.push_mock(&mock_ready),
                    queue.ready_wakers.push_mock(&mock_ready),
                    queue.ready_wakers.push_mock(&mock_ready),
                ];
                mock_pop_ready_cursors = [
                    queue.pop_ready_wakers.push_mock(&mock_pop_ready),
                    queue.pop_ready_wakers.push_mock(&mock_pop_ready),
                    queue.pop_ready_wakers.push_mock(&mock_pop_ready),
                    queue.pop_ready_wakers.push_mock(&mock_pop_ready),
                    queue.pop_ready_wakers.push_mock(&mock_pop_ready),
                ];
            }
            Self {
                queue,
                mock,
                mock_ready,
                mock_ready_cursors,
                mock_pop_ready,
                mock_pop_ready_cursors,
            }
        }

        fn assert<const M0: usize, const M1: usize>(
            &self,
            expect_closed: bool,
            expect_lens: (usize, usize, usize, usize), // polling, current, pending, ready
            expect_wakers: ([bool; M0], [bool; M1]),
            expect_num_wakeups: (usize, usize, usize),
        ) {
            self.queue
                .must_lock()
                .assert(expect_closed, expect_lens, expect_wakers);
            assert_eq!(self.mock.mock_waker.get(), expect_num_wakeups.0);
            assert_eq!(self.mock_ready.mock_waker.get(), expect_num_wakeups.1);
            assert_eq!(self.mock_pop_ready.mock_waker.get(), expect_num_wakeups.2);
        }

        fn rearm_wakers(&mut self) {
            let mut queue = self.queue.must_lock();
            for cursor in self.mock_ready_cursors {
                queue.ready_wakers.rearm_waker(cursor, &self.mock_ready);
            }
            for cursor in self.mock_pop_ready_cursors {
                queue
                    .pop_ready_wakers
                    .rearm_waker(cursor, &self.mock_pop_ready);
            }
        }

        fn reset_mocks(&self) {
            self.mock.mock_waker.reset();
            self.mock_ready.mock_waker.reset();
            self.mock_pop_ready.mock_waker.reset();
        }
    }

    macro_rules! test_ready {
        ($test:ident, $expect:expr $(,)?) => {{
            let mut poller = Ready::new($test.queue.clone());
            assert_eq!(
                Pin::new(&mut poller).poll(&mut $test.mock.context()),
                $expect,
            );
            poller
        }};
    }

    macro_rules! test_pop_ready {
        ($test:ident, $expect:pat $(,)?) => {{
            let mut poller = PopReady::new($test.queue.clone());
            assert!(matches!(
                Pin::new(&mut poller).poll(&mut $test.mock.context()),
                $expect,
            ));
            poller
        }};
    }

    #[test]
    fn ready() {
        let mut test = Test::new([Box::pin(future::ready(101)), Box::pin(future::ready(102))]);
        test.assert(false, (2, 0, 0, 0), ([true; 5], [true; 5]), (0, 0, 0));

        test_ready!(test, Poll::Ready(()));
        test.assert(
            false,
            (0, 0, 0, 2),
            // There are two `false` values because there are two futures that are ready.
            ([false; 5], [false, false, true, true, true]),
            (0, 5, 2),
        );

        test.rearm_wakers();
        test.reset_mocks();
        for _ in 0..3 {
            test_ready!(test, Poll::Ready(()));
            test.assert(false, (0, 0, 0, 2), ([true; 5], [true; 5]), (0, 0, 0));
        }

        let mut test = Test::new([Box::pin(future::ready(101)), Box::pin(future::ready(102))]);
        test.assert(false, (2, 0, 0, 0), ([true; 5], [true; 5]), (0, 0, 0));

        test_pop_ready!(test, Poll::Ready(Some((101, _))));
        test.assert(
            false,
            (0, 0, 0, 1),
            // There are three `false` values because there are two futures that are ready plus one
            // `Queue::pop_ready` call.
            ([false; 5], [false, false, false, true, true]),
            (0, 5, 3),
        );

        test.rearm_wakers();
        test.reset_mocks();
        test_pop_ready!(test, Poll::Ready(Some((102, _))));
        test.assert(false, (0, 0, 0, 0), ([true; 5], [true; 5]), (0, 0, 0));

        for _ in 0..3 {
            test_pop_ready!(test, Poll::Pending);
            test.assert(false, (0, 0, 0, 0), ([true; 5], [true; 5]), (0, 0, 0));
        }
    }

    #[test]
    fn pending() {
        let test = Test::new([Box::pin(future::pending()), Box::pin(future::pending())]);
        test_ready!(test, Poll::Pending);
        test.assert(false, (0, 0, 2, 0), ([true; 5], [true; 5]), (0, 0, 0));

        let test = Test::new([Box::pin(future::pending()), Box::pin(future::pending())]);
        test_pop_ready!(test, Poll::Pending);
        test.assert(false, (0, 0, 2, 0), ([true; 5], [true; 5]), (0, 0, 0));
    }

    #[test]
    fn pending_yield() {
        let test = Test::new([Box::pin(Yield::new()), Box::pin(future::ready(101))]);
        let poller = test_ready!(test, Poll::Pending);
        test.assert(
            false,
            (2, 0, 0, 0),
            ([true, true, true, true, true, false], [true; 5]),
            (1, 0, 0),
        );
        drop(poller);
        test.assert(
            false,
            (2, 0, 0, 0),
            ([false, true, true, true, true], [true; 5]),
            (1, 1, 0),
        );

        let test = Test::new([Box::pin(Yield::new()), Box::pin(future::ready(101))]);
        let poller = test_pop_ready!(test, Poll::Pending);
        test.assert(
            false,
            (2, 0, 0, 0),
            ([true; 5], [true, true, true, true, true, false]),
            (1, 0, 0),
        );
        drop(poller);
        test.assert(
            false,
            (2, 0, 0, 0),
            ([false, true, true, true, true], [true; 5]),
            (1, 1, 0),
        );
    }

    #[test]
    fn close() {
        let test = Test::new([]);
        test_ready!(test, Poll::Pending);
        test.queue.must_lock().close();
        test_ready!(test, Poll::Ready(()));

        let test = Test::new([Box::pin(future::pending())]);
        test.queue.must_lock().close();
        test_ready!(test, Poll::Pending);

        let test = Test::new([]);
        test_pop_ready!(test, Poll::Pending);
        test.queue.must_lock().close();
        test_pop_ready!(test, Poll::Ready(None));

        let test = Test::new([Box::pin(future::pending())]);
        test.queue.must_lock().close();
        test_pop_ready!(test, Poll::Pending);
    }

    #[test]
    fn pathological_case() {
        let test = Test::new([]);
        let poller = test_ready!(test, Poll::Pending);
        test.assert(false, (0, 0, 0, 0), ([true; 6], [true; 5]), (0, 0, 0));

        // While this does not wake up `poller`, let us pretend it is `poller`.
        test.queue
            .must_lock()
            .push_polling(Box::pin(future::ready(101)));
        test.assert(
            false,
            (1, 0, 0, 0),
            ([false, true, true, true, true, true], [true; 5]),
            (0, 1, 0),
        );

        // `poller` is awakened but it is dropped without being polled.
        drop(poller);
        test.assert(
            false,
            (1, 0, 0, 0),
            // Another task is awakened.
            ([false, false, true, true, true], [true; 5]),
            (0, 2, 0),
        );

        let test = Test::new([]);
        let poller = test_pop_ready!(test, Poll::Pending);
        test.assert(false, (0, 0, 0, 0), ([true; 5], [true; 6]), (0, 0, 0));

        // While this does not wake up `poller`, let us pretend it is `poller`.
        test.queue
            .must_lock()
            .push_polling(Box::pin(future::ready(101)));
        test.assert(
            false,
            (1, 0, 0, 0),
            ([false, true, true, true, true], [true; 6]),
            (0, 1, 0),
        );

        // `poller` is awakened but it is dropped without being polled.
        drop(poller);
        test.assert(
            false,
            (1, 0, 0, 0),
            // Another task is awakened.
            ([false, false, true, true, true], [true; 5]),
            (0, 2, 0),
        );
    }
}
