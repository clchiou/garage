use std::collections::{HashMap, VecDeque};
use std::sync::MutexGuard;
use std::task::{Context, Waker};

use crate::task;

pub(super) type Id = u64;

#[derive(Debug)]
pub(super) struct ReadyQueueImpl<T, F> {
    pub(super) closed: bool,
    next_id: u64,
    polling: VecDeque<(Id, F)>,
    current_id: Option<Id>,
    pending: HashMap<Id, F>,
    ready: VecDeque<(T, F)>,
    waker: Option<Waker>,
}

impl<T, F> ReadyQueueImpl<T, F> {
    pub(super) fn new() -> Self {
        Self {
            closed: false,
            next_id: 0,
            polling: VecDeque::new(),
            current_id: None,
            pending: HashMap::new(),
            ready: VecDeque::new(),
            waker: None,
        }
    }

    pub(super) fn len(&self) -> usize {
        self.polling.len()
            + usize::from(self.current_id.is_some())
            + self.pending.len()
            + self.ready.len()
    }

    pub(super) fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub(super) fn detach_all(&mut self) -> Vec<F> {
        let mut futures = Vec::with_capacity(self.polling.len() + self.pending.len());
        futures.extend(self.polling.drain(..).map(|(_, future)| future));
        futures.extend(self.pending.drain().map(|(_, future)| future));
        futures
    }

    pub(super) fn update_waker(&mut self, context: &Context) {
        task::update_waker(&mut self.waker, context);
    }

    pub(super) fn wake(mut this: MutexGuard<'_, Self>) {
        if let Some(waker) = this.waker.take() {
            drop(this);
            waker.wake();
        }
    }

    //
    // future --+--> polling --> current future --+--> ready
    //          ^                                 |
    //          |                                 |
    //          +------------ pending <-----------+
    //
    // NOTE: `Future::poll` might call `FutureWaker::wake_by_ref`, and it could do so multiple
    // times.  Therefore, `move_to_pending,` `move_to_ready,` `move_to_polling`, and
    // `return_polling` have to handle such case.
    //

    fn next_id(&mut self) -> Id {
        let id = self.next_id;
        self.next_id += 1;
        id
    }

    /// Adds a new future to `polling`.
    pub(super) fn push_polling(mut this: MutexGuard<'_, Self>, future: F) {
        let id = this.next_id();
        this.polling.push_back((id, future));
        Self::wake(this);
    }

    /// Removes a future from `polling` and designates it as the current future.
    pub(super) fn move_to_current(&mut self) -> Option<(Id, F)> {
        self.polling.pop_front().inspect(|(id, _)| {
            assert!(self.current_id.is_none());
            self.current_id = Some(*id);
        })
    }

    /// Moves the current future to `ready`.
    // This is called by `ReadyQeueu::poll_pop_ready_with_future`.
    pub(super) fn move_to_ready(&mut self, id: Id, value: T, future: F) {
        assert_eq!(self.current_id.take().unwrap_or(id), id);
        self.ready.push_back((value, future));
    }

    /// Moves the current future to `pending`.
    // This is called by `ReadyQeueu::poll_pop_ready_with_future`.
    pub(super) fn move_to_pending(&mut self, id: Id, future: F) -> Result<(), (Id, F)> {
        match self.current_id.take() {
            Some(current_id) => {
                assert_eq!(current_id, id);
                assert!(self.pending.insert(id, future).is_none());
                Ok(())
            }
            None => Err((id, future)),
        }
    }

    /// Returns the current future to `polling`.
    // This is called by `ReadyQeueu::poll_pop_ready_with_future`.
    pub(super) fn return_polling(&mut self, id: Id, future: F) {
        assert!(self.current_id.is_none());
        self.polling.push_back((id, future));
    }

    /// Moves a future from `pending` to `polling`.
    // This is called by `FutureWaker::wake_by_ref`.
    pub(super) fn move_to_polling(&mut self, id: Id) {
        match self.pending.remove(&id) {
            Some(future) => self.polling.push_back((id, future)),
            None => assert_eq!(self.current_id.take().unwrap_or(id), id),
        }
    }

    /// Removes a future from `ready`.
    pub(super) fn pop_ready(&mut self) -> Option<(T, F)> {
        self.ready.pop_front()
    }
}

#[cfg(test)]
pub(crate) mod test_harness {
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };
    use std::task::Wake;

    pub(crate) struct MockWaker(AtomicUsize);

    impl MockWaker {
        pub(crate) fn new() -> Self {
            Self(AtomicUsize::new(0))
        }

        pub(crate) fn num_calls(&self) -> usize {
            self.0.load(Ordering::SeqCst)
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
}

#[cfg(test)]
mod tests {
    use std::fmt;
    use std::future;
    use std::sync::Arc;
    use std::task::Poll;

    use tokio::sync::Notify;

    use crate::sync::MutexExt;

    use super::{super::ReadyQueue, test_harness::MockWaker, *};

    fn assert_queue<T, F>(
        queue: &ReadyQueue<T, F>,
        closed: bool,
        next_id: Id,
        polling: &[Id],
        current_id: Option<Id>,
        pending: &[Id],
        ready: &[&T],
        waker: bool,
    ) where
        T: fmt::Debug + PartialEq,
    {
        let queue = queue.0.must_lock();
        assert_eq!(queue.closed, closed);
        assert_eq!(queue.next_id, next_id);
        assert_eq!(
            queue.polling.iter().map(|(id, _)| *id).collect::<Vec<_>>(),
            polling,
        );
        assert_eq!(queue.current_id, current_id);
        let mut pending_ids: Vec<_> = queue.pending.keys().copied().collect();
        pending_ids.sort();
        assert_eq!(pending_ids, pending);
        assert_eq!(
            queue
                .ready
                .iter()
                .map(|(value, _)| value)
                .collect::<Vec<_>>(),
            ready,
        );
        assert_eq!(queue.waker.is_some(), waker);
    }

    #[test]
    fn poll_pop_ready_with_future() {
        let mock_waker = Arc::new(MockWaker::new());
        let waker = Waker::from(mock_waker.clone());
        let mut context = Context::from_waker(&waker);
        assert_eq!(mock_waker.num_calls(), 0);

        let notify = Arc::new(Notify::new());

        let queue = ReadyQueue::new();
        assert_queue(&queue, false, 0, &[], None, &[], &[], false);

        assert!(matches!(queue.push(future::pending()), Ok(())));
        assert_queue(&queue, false, 1, &[0], None, &[], &[], false);

        assert!(matches!(queue.push(async { 100usize }), Ok(())));
        assert_queue(&queue, false, 2, &[0, 1], None, &[], &[], false);

        {
            let notify = notify.clone();
            assert!(matches!(
                queue.push(async move {
                    notify.notified().await;
                    101usize
                }),
                Ok(()),
            ));
        }
        assert_queue(&queue, false, 3, &[0, 1, 2], None, &[], &[], false);

        assert!(matches!(queue.push(async { 102usize }), Ok(())));
        assert_queue(&queue, false, 4, &[0, 1, 2, 3], None, &[], &[], false);

        assert!(matches!(
            queue.poll_pop_ready_with_future(&mut context),
            Poll::Ready(Some((100, _))),
        ));
        assert_queue(&queue, false, 4, &[], None, &[0, 2], &[&102], false);
        assert_eq!(mock_waker.num_calls(), 0);

        assert!(matches!(
            queue.poll_pop_ready_with_future(&mut context),
            Poll::Ready(Some((102, _))),
        ));
        assert_queue(&queue, false, 4, &[], None, &[0, 2], &[], false);
        assert_eq!(mock_waker.num_calls(), 0);

        assert!(matches!(
            queue.poll_pop_ready_with_future(&mut context),
            Poll::Pending,
        ));
        assert_queue(&queue, false, 4, &[], None, &[0, 2], &[], true);
        assert_eq!(mock_waker.num_calls(), 0);

        notify.notify_one();
        assert_queue(&queue, false, 4, &[2], None, &[0], &[], false);
        assert_eq!(mock_waker.num_calls(), 1);

        assert!(matches!(
            queue.poll_pop_ready_with_future(&mut context),
            Poll::Ready(Some((101, _))),
        ));
        assert_queue(&queue, false, 4, &[], None, &[0], &[], false);
        assert_eq!(mock_waker.num_calls(), 1);
    }

    #[test]
    fn move_to_polling_called_by_waker() {
        let queue = ReadyQueue::<()>::new();
        assert!(matches!(queue.push(future::pending()), Ok(())));
        assert!(matches!(queue.push(future::pending()), Ok(())));
        assert!(matches!(queue.push(future::pending()), Ok(())));
        assert_queue(&queue, false, 3, &[0, 1, 2], None, &[], &[], false);

        // move_to_ready
        {
            let (id, future) = queue.0.must_lock().move_to_current().unwrap();
            assert_eq!(id, 0);
            assert_queue(&queue, false, 3, &[1, 2], Some(0), &[], &[], false);

            for _ in 0..3 {
                queue.0.must_lock().move_to_polling(0);
                assert_queue(&queue, false, 3, &[1, 2], None, &[], &[], false);
            }

            queue.0.must_lock().move_to_ready(id, (), future);
            assert_queue(&queue, false, 3, &[1, 2], None, &[], &[&()], false);

            assert!(matches!(queue.0.must_lock().pop_ready(), Some(((), _))));
            assert_queue(&queue, false, 3, &[1, 2], None, &[], &[], false);
        }

        // move_to_pending
        {
            let (id, future) = queue.0.must_lock().move_to_current().unwrap();
            assert_eq!(id, 1);
            assert_queue(&queue, false, 3, &[2], Some(1), &[], &[], false);

            for _ in 0..3 {
                queue.0.must_lock().move_to_polling(1);
                assert_queue(&queue, false, 3, &[2], None, &[], &[], false);
            }

            let error = queue.0.must_lock().move_to_pending(id, future).unwrap_err();
            assert_eq!(error.0, id);
            assert_queue(&queue, false, 3, &[2], None, &[], &[], false);

            queue.0.must_lock().return_polling(error.0, error.1);
            assert_queue(&queue, false, 3, &[2, 1], None, &[], &[], false);

            assert!(matches!(queue.0.must_lock().pop_ready(), None));
            assert_queue(&queue, false, 3, &[2, 1], None, &[], &[], false);
        }
    }

    #[test]
    fn move_to_ready() {
        let queue = ReadyQueue::<()>::new();
        assert!(matches!(queue.push(future::pending()), Ok(())));
        assert!(matches!(queue.push(future::pending()), Ok(())));
        assert_queue(&queue, false, 2, &[0, 1], None, &[], &[], false);

        let (id, future) = queue.0.must_lock().move_to_current().unwrap();
        assert_eq!(id, 0);
        assert_queue(&queue, false, 2, &[1], Some(0), &[], &[], false);

        queue.0.must_lock().move_to_ready(id, (), future);
        assert_queue(&queue, false, 2, &[1], None, &[], &[&()], false);

        assert!(matches!(queue.0.must_lock().pop_ready(), Some(((), _))));
        assert_queue(&queue, false, 2, &[1], None, &[], &[], false);

        for _ in 0..3 {
            queue.0.must_lock().move_to_polling(0);
            assert_queue(&queue, false, 2, &[1], None, &[], &[], false);
        }
    }

    #[test]
    fn move_to_pending() {
        let queue = ReadyQueue::<()>::new();
        assert!(matches!(queue.push(future::pending()), Ok(())));
        assert!(matches!(queue.push(future::pending()), Ok(())));
        assert_queue(&queue, false, 2, &[0, 1], None, &[], &[], false);

        let (id, future) = queue.0.must_lock().move_to_current().unwrap();
        assert_eq!(id, 0);
        assert_queue(&queue, false, 2, &[1], Some(0), &[], &[], false);

        assert!(matches!(
            queue.0.must_lock().move_to_pending(id, future),
            Ok(()),
        ));
        assert_queue(&queue, false, 2, &[1], None, &[0], &[], false);

        assert!(matches!(queue.0.must_lock().pop_ready(), None));
        assert_queue(&queue, false, 2, &[1], None, &[0], &[], false);

        for _ in 0..3 {
            queue.0.must_lock().move_to_polling(0);
            assert_queue(&queue, false, 2, &[1, 0], None, &[], &[], false);
        }
    }
}
