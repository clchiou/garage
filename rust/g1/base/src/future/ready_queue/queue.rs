use std::collections::VecDeque;
use std::task::{Context, Waker};

use crate::{
    collections::vec_list::{Cursor, VecList},
    task,
};

/// Future queue and wakers for each async function call.
///
/// Below is the state transition for a future object:
///
/// input --+--> polling --> current --+--> ready --> output
///         ^                          |
///         |                          |
///         +-------- pending <--------+
///
/// Suppose there are `N` pending futures and `M` async function calls.  We need to manage the
/// mapping from `N` future wakers to `M` async wakers.  Be cautious, as there are two groups of
/// wakers; do not be confused.
///
/// Below is when async function calls should be awaken:
///
/// |                       | ready_wakers | pop_ready_wakers |
/// | --------------------- | ------------ | ---------------- |
/// | has_polling           | one                            ||
/// | has_ready             | all          | one              |
/// | is_closed && is_empty | all                            ||
///
/// NOTE: For efficiency, when `has_polling`, we wake up only one task to poll the futures.
/// However, we must handle the pathological case where the task fails to poll upon awakening (by
/// waking up another task).
#[derive(Debug)]
pub(super) struct Queue<T, Fut> {
    closed: bool,

    // `VecList` nodes can be reused, and we use serial numbers to detect this.
    next_serial: u64,
    polling: VecDeque<Fut>,
    pending: VecList<(u64, Option<Fut>)>,
    ready: VecDeque<(T, Fut)>,

    // TODO: For the ease of implementation, we call these wakers while holding the lock.  I am not
    // sure if this will cause a deadlock, but I guess it probably will not.  Figure out whether we
    // should release the lock before calling these wakers.
    pub(super) ready_wakers: Wakers,
    pub(super) pop_ready_wakers: Wakers,
}

pub(super) type Id = (Cursor, u64);

#[derive(Debug)]
pub(super) struct Wakers(VecList<Option<Waker>>);

impl<T, Fut> Queue<T, Fut> {
    pub(super) fn new() -> Self {
        Self {
            closed: false,

            next_serial: 0,
            polling: VecDeque::new(),
            pending: VecList::new(),
            ready: VecDeque::new(),

            ready_wakers: Wakers::new(),
            pop_ready_wakers: Wakers::new(),
        }
    }

    pub(super) fn is_closed(&self) -> bool {
        self.closed
    }

    pub(super) fn close(&mut self) {
        self.closed = true;
        if self.is_empty() {
            self.wake_all();
        }
    }

    pub(super) fn len(&self) -> usize {
        self.polling.len() + self.pending.len() + self.ready.len()
    }

    pub(super) fn is_empty(&self) -> bool {
        self.polling.is_empty() && self.pending.is_empty() && self.ready.is_empty()
    }

    pub(super) fn is_ready(&self) -> bool {
        self.has_ready() || (self.is_closed() && self.is_empty())
    }

    pub(super) fn has_polling(&self) -> bool {
        !self.polling.is_empty()
    }

    fn has_ready(&self) -> bool {
        !self.ready.is_empty()
    }

    pub(super) fn detach_all(&mut self) -> Vec<Fut> {
        let mut futures = Vec::with_capacity(self.polling.len() + self.pending.len());

        futures.extend(self.polling.drain(..));

        let mut p = self.pending.cursor_front();
        while let Some(cursor) = p {
            p = self.pending.move_next(cursor);
            if self.pending[cursor].1.is_some() {
                futures.push(self.pending.remove(cursor).1.unwrap());
            }
        }

        if self.is_closed() && self.is_empty() {
            self.wake_all();
        }
        futures
    }

    fn next_serial(&mut self) -> u64 {
        let serial = self.next_serial;
        self.next_serial += 1;
        serial
    }

    fn contains_pending(&self, (cursor, serial): Id) -> bool {
        self.pending
            .get(cursor)
            .map(|pending| pending.0 == serial)
            .unwrap_or(false)
    }

    fn get_pending_mut(&mut self, (cursor, serial): Id) -> Option<&mut (u64, Option<Fut>)> {
        let pending = self.pending.get_mut(cursor)?;
        (pending.0 == serial).then_some(pending)
    }

    //
    // Future State Transition Methods
    //

    /// input -> polling
    pub(super) fn push_polling(&mut self, future: Fut) {
        self.polling.push_back(future);
        self.wake_one();
    }

    /// polling -> current
    pub(super) fn next_polling(&mut self) -> Option<(Id, Fut)> {
        // Reserve a spot in `pending` for the current future.
        let future = self.polling.pop_front()?;
        let serial = self.next_serial();
        let cursor = self.pending.push_back((serial, None));
        Some(((cursor, serial), future))
    }

    /// current -> ready
    pub(super) fn push_ready(&mut self, id: Id, value: T, future: Fut) {
        // Remove the reserved spot in `pending`.
        let pending = self.get_pending_mut(id).unwrap();
        assert!(pending.1.is_none());
        self.pending.remove(id.0);

        self.ready.push_back((value, future));
        self.ready_wakers.wake_all();
        self.pop_ready_wakers.wake_one();
    }

    /// current -> pending
    pub(super) fn push_pending(&mut self, id: Id, future: Fut) -> Result<(), Fut> {
        let Some(pending) = self.get_pending_mut(id) else {
            // `resume_polling` was called, which indicates that this task should yield.
            return Err(future);
        };
        // `push_pending` should be called at most once per current future.
        assert!(pending.1.is_none());
        pending.1 = Some(future);
        Ok(())
    }

    /// pending -> polling
    ///
    /// This is called only by `FutureWaker`.
    pub(super) fn resume_polling(&mut self, id: Id) {
        // `resume_polling` can be called multiple times.
        if !self.contains_pending(id) {
            return;
        }
        // Remove the reserved spot in `pending`.
        let (_, Some(future)) = self.pending.remove(id.0) else {
            // `resume_polling` is called before `push_pending`, which indicates that this task
            // should yield.
            return;
        };
        self.polling.push_back(future);
        self.wake_one();
    }

    /// current -(pending)-> polling
    ///
    /// This is called only when `push_pending` returns `Err`.
    pub(super) fn resume_polling_after_yield(&mut self, future: Fut) {
        self.polling.push_front(future);
    }

    /// ready -> output
    pub(super) fn pop_ready(&mut self) -> Option<(T, Fut)> {
        self.ready.pop_front().inspect(|_| {
            if self.has_ready() {
                self.ready_wakers.wake_all();
                self.pop_ready_wakers.wake_one();
            } else if self.is_closed() && self.is_empty() {
                self.wake_all();
            }
        })
    }

    //
    // Waker Methods
    //

    fn wake_all(&mut self) {
        self.ready_wakers.wake_all();
        self.pop_ready_wakers.wake_all();
    }

    pub(super) fn wake_one(&mut self) -> bool {
        self.ready_wakers.wake_one() || self.pop_ready_wakers.wake_one()
    }
}

impl Wakers {
    fn new() -> Self {
        Self(VecList::new())
    }

    fn wake_all(&mut self) {
        Self::for_each(self.0.cursor_front(), |cursor| {
            if let Some(waker) = self.take_waker(cursor) {
                waker.wake();
            }
            self.0.move_next(cursor)
        });
    }

    fn wake_one(&mut self) -> bool {
        let mut succeed = false;
        Self::for_each(self.0.cursor_front(), |cursor| {
            match self.take_waker(cursor) {
                Some(waker) => {
                    waker.wake();
                    succeed = true;
                    None
                }
                None => self.0.move_next(cursor),
            }
        });
        succeed
    }

    fn for_each<F>(mut p: Option<Cursor>, mut f: F)
    where
        F: FnMut(Cursor) -> Option<Cursor>,
    {
        while let Some(cursor) = p {
            p = f(cursor);
        }
    }

    fn take_waker(&mut self, cursor: Cursor) -> Option<Waker> {
        self.0[cursor].take()
    }

    pub(super) fn reserve(&mut self) -> Cursor {
        self.0.push_back(None)
    }

    pub(super) fn update(&mut self, cursor: Cursor, context: &Context) {
        task::update_waker(&mut self.0[cursor], context);
    }

    pub(super) fn remove(&mut self, cursor: Cursor) -> Option<Waker> {
        self.0.remove(cursor)
    }
}

#[cfg(test)]
pub(crate) mod test_harness {
    use super::{super::test_harness::MockContext, *};

    impl<T, Fut> Queue<T, Fut> {
        pub(crate) fn assert<const M0: usize, const M1: usize>(
            &self,
            expect_closed: bool,
            expect_lens: (usize, usize, usize, usize), // polling, current, pending, ready
            expect_wakers: ([bool; M0], [bool; M1]),
        ) {
            assert_eq!(self.is_closed(), expect_closed);

            let expect_len = expect_lens.0 + expect_lens.1 + expect_lens.2 + expect_lens.3;
            assert_eq!(self.len(), expect_len);
            assert_eq!(self.is_empty(), expect_len == 0);

            assert_eq!(
                self.is_ready(),
                expect_lens.3 != 0 || (expect_closed && expect_len == 0),
            );
            assert_eq!(self.has_polling(), expect_lens.0 != 0);
            assert_eq!(self.has_ready(), expect_lens.3 != 0);

            assert_eq!(self.polling.len(), expect_lens.0);
            assert_eq!(
                self.pending
                    .iter()
                    .filter(|pending| pending.1.is_none())
                    .count(),
                expect_lens.1,
            );
            assert_eq!(
                self.pending
                    .iter()
                    .filter(|pending| pending.1.is_some())
                    .count(),
                expect_lens.2,
            );
            assert_eq!(self.ready.len(), expect_lens.3);

            self.ready_wakers.assert(expect_wakers.0);
            self.pop_ready_wakers.assert(expect_wakers.1);
        }
    }

    impl Wakers {
        pub(crate) fn push_mock(&mut self, mock: &MockContext) -> Cursor {
            let cursor = self.reserve();
            self.update(cursor, &mock.context());
            cursor
        }

        pub(crate) fn assert<const M: usize>(&self, expect: [bool; M]) {
            let actual: Vec<_> = self.0.iter().map(|w| w.is_some()).collect();
            assert_eq!(actual, expect);
        }

        pub(crate) fn rearm_waker(&mut self, cursor: Cursor, mock: &MockContext) {
            self.update(cursor, &mock.context());
        }
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use super::{super::test_harness::MockContext, *};

    struct Test {
        queue: Queue<(), usize>,

        mock_ready: MockContext,
        mock_ready_cursors: [Cursor; 2],

        mock_pop_ready: MockContext,
        mock_pop_ready_cursors: [Cursor; 2],
    }

    impl Test {
        fn new<const N: usize>(futures: [usize; N]) -> Self {
            let mut queue = Queue::new();
            for future in futures {
                queue.push_polling(future);
            }
            let mock_ready = MockContext::new();
            let mock_ready_cursors = [
                queue.ready_wakers.push_mock(&mock_ready),
                queue.ready_wakers.push_mock(&mock_ready),
            ];
            let mock_pop_ready = MockContext::new();
            let mock_pop_ready_cursors = [
                queue.pop_ready_wakers.push_mock(&mock_pop_ready),
                queue.pop_ready_wakers.push_mock(&mock_pop_ready),
            ];
            Self {
                queue,
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
            expect_num_wakeups: (usize, usize),
        ) {
            self.queue.assert(expect_closed, expect_lens, expect_wakers);
            assert_eq!(self.mock_ready.mock_waker.get(), expect_num_wakeups.0);
            assert_eq!(self.mock_pop_ready.mock_waker.get(), expect_num_wakeups.1);
        }

        fn rearm_wakers(&mut self) {
            for cursor in self.mock_ready_cursors {
                self.queue
                    .ready_wakers
                    .rearm_waker(cursor, &self.mock_ready);
            }
            for cursor in self.mock_pop_ready_cursors {
                self.queue
                    .pop_ready_wakers
                    .rearm_waker(cursor, &self.mock_pop_ready);
            }
        }

        fn reset_mocks(&self) {
            self.mock_ready.mock_waker.reset();
            self.mock_pop_ready.mock_waker.reset();
        }
    }

    #[test]
    fn close() {
        let mut test = Test::new([101]);
        test.queue.close();
        test.assert(true, (1, 0, 0, 0), ([true; 2], [true; 2]), (0, 0));

        let mut test = Test::new([]);
        test.queue.close();
        test.assert(true, (0, 0, 0, 0), ([false; 2], [false; 2]), (2, 2));
    }

    #[test]
    fn future_state() {
        let mut test = Test::new([]);
        test.assert(false, (0, 0, 0, 0), ([true; 2], [true; 2]), (0, 0));

        test.queue.push_polling(101);
        test.assert(false, (1, 0, 0, 0), ([false, true], [true; 2]), (1, 0));
        test.rearm_wakers();

        let (id, fut) = test.queue.next_polling().unwrap();
        assert_eq!(fut, 101);
        test.assert(false, (0, 1, 0, 0), ([true; 2], [true; 2]), (1, 0));

        assert_eq!(test.queue.push_pending(id, fut), Ok(()));
        test.assert(false, (0, 0, 1, 0), ([true; 2], [true; 2]), (1, 0));

        test.queue.resume_polling(id);
        test.assert(false, (1, 0, 0, 0), ([false, true], [true; 2]), (2, 0));
        test.rearm_wakers();

        let (id, fut) = test.queue.next_polling().unwrap();
        assert_eq!(fut, 101);
        test.assert(false, (0, 1, 0, 0), ([true; 2], [true; 2]), (2, 0));

        test.queue.push_ready(id, (), fut);
        test.assert(false, (0, 0, 0, 1), ([false; 2], [false, true]), (4, 1));
        test.rearm_wakers();

        assert_eq!(test.queue.pop_ready(), Some(((), fut)));
        test.assert(false, (0, 0, 0, 0), ([true; 2], [true; 2]), (4, 1));
    }

    #[test]
    fn detach_all() {
        let mut test = Test::new([101, 102, 103, 104]);
        let (id1, fut1) = test.queue.next_polling().unwrap();
        let (id2, fut2) = test.queue.next_polling().unwrap();
        let _ = test.queue.next_polling().unwrap();
        test.queue.push_ready(id1, (), fut1);
        assert_eq!(test.queue.push_pending(id2, fut2), Ok(()));
        test.rearm_wakers();
        test.reset_mocks();
        test.assert(false, (1, 1, 1, 1), ([true; 2], [true; 2]), (0, 0));
        assert_eq!(test.queue.polling, [104]);
        assert_eq!(test.queue.pending, [(1, Some(102)), (2, None)].into());
        assert_eq!(test.queue.ready, [((), 101)]);

        assert_eq!(test.queue.detach_all(), [104, 102]);
        test.assert(false, (0, 1, 0, 1), ([true; 2], [true; 2]), (0, 0));
        assert_eq!(test.queue.polling, []);
        assert_eq!(test.queue.pending, [(2, None)].into());
        assert_eq!(test.queue.ready, [((), 101)]);

        assert_eq!(test.queue.detach_all(), []);
        test.assert(false, (0, 1, 0, 1), ([true; 2], [true; 2]), (0, 0));

        let mut test = Test::new([101]);
        assert_eq!(test.queue.detach_all(), [101]);
        test.assert(false, (0, 0, 0, 0), ([true; 2], [true; 2]), (0, 0));

        let mut test = Test::new([101]);
        test.queue.close();
        test.rearm_wakers();
        test.reset_mocks();
        test.assert(true, (1, 0, 0, 0), ([true; 2], [true; 2]), (0, 0));
        assert_eq!(test.queue.detach_all(), [101]);
        test.assert(true, (0, 0, 0, 0), ([false; 2], [false; 2]), (2, 2));
    }

    #[test]
    fn next_serial() {
        let mut queue = Queue::<(), ()>::new();
        for expect in 0..10 {
            assert_eq!(queue.next_serial, expect);
            assert_eq!(queue.next_serial(), expect);
        }
        assert_eq!(queue.next_serial, 10);
    }

    #[test]
    fn pending() {
        let mut queue = Queue::<(), usize>::new();
        queue.push_polling(101);
        queue.push_polling(102);
        let ((c0, s0), _) = queue.next_polling().unwrap();
        let ((c1, s1), _) = queue.next_polling().unwrap();

        assert_eq!(queue.contains_pending((c0, s0)), true);
        assert_eq!(queue.contains_pending((c0, s1)), false);
        assert_eq!(queue.contains_pending((c1, s0)), false);
        assert_eq!(queue.contains_pending((c1, s1)), true);

        assert_eq!(queue.get_pending_mut((c0, s0)), Some(&mut (s0, None)));
        assert_eq!(queue.get_pending_mut((c0, s1)), None);
        assert_eq!(queue.get_pending_mut((c1, s0)), None);
        assert_eq!(queue.get_pending_mut((c1, s1)), Some(&mut (s1, None)));
    }

    #[test]
    fn push_polling() {
        let mut test = Test::new([]);
        test.assert(false, (0, 0, 0, 0), ([true; 2], [true; 2]), (0, 0));

        test.queue.push_polling(101);
        test.assert(false, (1, 0, 0, 0), ([false, true], [true; 2]), (1, 0));
        assert_eq!(test.queue.polling, [101]);

        test.queue.push_polling(102);
        test.assert(false, (2, 0, 0, 0), ([false, false], [true; 2]), (2, 0));
        assert_eq!(test.queue.polling, [101, 102]);

        test.queue.push_polling(103);
        test.assert(false, (3, 0, 0, 0), ([false, false], [false, true]), (2, 1));
        assert_eq!(test.queue.polling, [101, 102, 103]);
    }

    #[test]
    fn next_polling() {
        let mut test = Test::new([101, 102]);
        test.assert(false, (2, 0, 0, 0), ([true; 2], [true; 2]), (0, 0));

        assert_matches!(test.queue.next_polling(), Some(((_, 0), 101)));
        test.assert(false, (1, 1, 0, 0), ([true; 2], [true; 2]), (0, 0));
        assert_eq!(test.queue.pending, [(0, None)].into());

        assert_matches!(test.queue.next_polling(), Some(((_, 1), 102)));
        test.assert(false, (0, 2, 0, 0), ([true; 2], [true; 2]), (0, 0));
        assert_eq!(test.queue.pending, [(0, None), (1, None)].into());

        for _ in 0..3 {
            assert_eq!(test.queue.next_polling(), None);
            test.assert(false, (0, 2, 0, 0), ([true; 2], [true; 2]), (0, 0));
            assert_eq!(test.queue.pending, [(0, None), (1, None)].into());
        }
    }

    #[test]
    fn push_ready() {
        let mut test = Test::new([101]);
        let (id, fut) = test.queue.next_polling().unwrap();
        test.assert(false, (0, 1, 0, 0), ([true; 2], [true; 2]), (0, 0));

        test.queue.push_ready(id, (), fut);
        test.assert(false, (0, 0, 0, 1), ([false; 2], [false, true]), (2, 1));
        assert_eq!(test.queue.ready, [((), fut)]);
    }

    #[test]
    #[should_panic(expected = "Option::unwrap()")]
    fn push_ready_more_than_once() {
        let mut test = Test::new([101]);
        let (id, fut) = test.queue.next_polling().unwrap();
        test.queue.push_ready(id, (), fut);
        test.queue.push_ready(id, (), fut); // Panic!
    }

    #[test]
    #[should_panic(expected = "assertion failed: pending.1.is_none()")]
    fn push_ready_after_push_pending() {
        let mut test = Test::new([101]);
        let (id, fut) = test.queue.next_polling().unwrap();
        assert_eq!(test.queue.push_pending(id, fut), Ok(()));
        test.queue.push_ready(id, (), fut); // Panic!
    }

    #[test]
    fn push_pending() {
        let mut test = Test::new([101]);
        let ((cursor, serial), fut) = test.queue.next_polling().unwrap();
        test.assert(false, (0, 1, 0, 0), ([true; 2], [true; 2]), (0, 0));
        assert_eq!(test.queue.pending, [(serial, None)].into());

        assert_eq!(test.queue.push_pending((cursor, serial), fut), Ok(()));
        test.assert(false, (0, 0, 1, 0), ([true; 2], [true; 2]), (0, 0));
        assert_eq!(test.queue.pending, [(serial, Some(fut))].into());

        assert_eq!(test.queue.push_pending((cursor, serial + 1), 999), Err(999));
        test.assert(false, (0, 0, 1, 0), ([true; 2], [true; 2]), (0, 0));
    }

    #[test]
    #[should_panic(expected = "assertion failed: pending.1.is_none()")]
    fn push_pending_more_than_once() {
        let mut test = Test::new([101]);
        let (id, fut) = test.queue.next_polling().unwrap();
        assert_eq!(test.queue.push_pending(id, fut), Ok(()));
        assert_eq!(test.queue.push_pending(id, fut), Ok(())); // Panic!
    }

    #[test]
    fn resume_polling() {
        let mut test = Test::new([101, 102]);
        let (id1, fut1) = test.queue.next_polling().unwrap();
        let (id2, fut2) = test.queue.next_polling().unwrap();
        assert_eq!(fut1, 101);
        assert_eq!(fut2, 102);
        assert_eq!(test.queue.push_pending(id2, fut2), Ok(()));
        test.assert(false, (0, 1, 1, 0), ([true; 2], [true; 2]), (0, 0));
        assert_eq!(test.queue.polling, []);
        assert_eq!(test.queue.pending, [(0, None), (1, Some(fut2))].into());

        // `resume_polling(id1)` is called before `push_pending`.
        for _ in 0..3 {
            test.queue.resume_polling(id1);
            test.assert(false, (0, 0, 1, 0), ([true; 2], [true; 2]), (0, 0));
            assert_eq!(test.queue.polling, []);
            assert_eq!(test.queue.pending, [(1, Some(fut2))].into());
        }

        // `resume_polling(id2)` is called after `push_pending`.
        for _ in 0..3 {
            test.queue.resume_polling(id2);
            test.assert(false, (1, 0, 0, 0), ([false, true], [true; 2]), (1, 0));
            assert_eq!(test.queue.polling, [fut2]);
            assert_eq!(test.queue.pending, [].into());
        }
    }

    #[test]
    fn resume_polling_after_yield() {
        let mut test = Test::new([]);
        test.assert(false, (0, 0, 0, 0), ([true; 2], [true; 2]), (0, 0));

        test.queue.resume_polling_after_yield(101);
        test.queue.resume_polling_after_yield(102);
        test.assert(false, (2, 0, 0, 0), ([true; 2], [true; 2]), (0, 0));
        assert_eq!(test.queue.polling, [102, 101]);
    }

    #[test]
    fn pop_ready() {
        let mut test = Test::new([]);
        test.queue.ready.push_back(((), 101));
        test.assert(false, (0, 0, 0, 1), ([true; 2], [true; 2]), (0, 0));

        assert_eq!(test.queue.pop_ready(), Some(((), 101)));
        test.assert(false, (0, 0, 0, 0), ([true; 2], [true; 2]), (0, 0));
        for _ in 0..3 {
            assert_eq!(test.queue.pop_ready(), None);
            test.assert(false, (0, 0, 0, 0), ([true; 2], [true; 2]), (0, 0));
        }

        let mut test = Test::new([]);
        test.queue.ready.push_back(((), 102));
        test.queue.ready.push_back(((), 103));
        test.assert(false, (0, 0, 0, 2), ([true; 2], [true; 2]), (0, 0));

        assert_eq!(test.queue.pop_ready(), Some(((), 102)));
        test.assert(false, (0, 0, 0, 1), ([false; 2], [false, true]), (2, 1));

        let mut test = Test::new([]);
        test.queue.ready.push_back(((), 104));
        test.queue.closed = true;
        test.assert(true, (0, 0, 0, 1), ([true; 2], [true; 2]), (0, 0));

        assert_eq!(test.queue.pop_ready(), Some(((), 104)));
        test.assert(true, (0, 0, 0, 0), ([false; 2], [false; 2]), (2, 2));
    }

    #[test]
    fn wake_all() {
        let mut test = Test::new([]);
        test.assert(false, (0, 0, 0, 0), ([true; 2], [true; 2]), (0, 0));

        for _ in 0..3 {
            test.queue.wake_all();
            test.assert(false, (0, 0, 0, 0), ([false; 2], [false; 2]), (2, 2));
        }
    }

    #[test]
    fn wake_one() {
        let mut test = Test::new([]);
        test.assert(false, (0, 0, 0, 0), ([true; 2], [true; 2]), (0, 0));

        assert_eq!(test.queue.wake_one(), true);
        test.assert(false, (0, 0, 0, 0), ([false, true], [true; 2]), (1, 0));

        assert_eq!(test.queue.wake_one(), true);
        test.assert(false, (0, 0, 0, 0), ([false, false], [true; 2]), (2, 0));

        assert_eq!(test.queue.wake_one(), true);
        test.assert(false, (0, 0, 0, 0), ([false, false], [false, true]), (2, 1));

        assert_eq!(test.queue.wake_one(), true);
        test.assert(false, (0, 0, 0, 0), ([false; 2], [false; 2]), (2, 2));

        for _ in 0..3 {
            assert_eq!(test.queue.wake_one(), false);
            test.assert(false, (0, 0, 0, 0), ([false; 2], [false; 2]), (2, 2));
        }
    }
}
