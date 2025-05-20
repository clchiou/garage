use std::time::Duration;

use tokio::time::{self, Instant};

use g1_base::future::ReadyQueue;

use super::join_guard::{self, Cancel, JoinGuard, SHUTDOWN_TIMEOUT, ShutdownError};

// It is easy to share `JoinQueue` among threads.  However, we do not implement `Clone` for
// `JoinQueue` because we have implemented `Drop` for `JoinQueue` and want to avoid the scenario
// where one of the clones cancels all tasks upon being dropped.
//
// If you need to create clones of `JoinQueue`, wrap it in `Arc` instead.
#[derive(Debug)]
pub struct JoinQueue<T> {
    guards: ReadyQueue<(), JoinGuard<T>>,
    cancel: Cancel,
}

impl<T> Drop for JoinQueue<T> {
    fn drop(&mut self) {
        // It is necessary to call `cancel` here for the same reason as in `JoinGuard::drop`.
        self.cancel();
    }
}

impl<T> Default for JoinQueue<T> {
    fn default() -> Self {
        Self::new()
    }
}

impl<T> JoinQueue<T> {
    pub fn new() -> Self {
        Self::with_cancel(Cancel::new())
    }

    pub fn with_cancel(cancel: Cancel) -> Self {
        Self {
            guards: ReadyQueue::new(),
            cancel,
        }
    }

    pub fn add_parent(&self, parent: Cancel) {
        self.cancel.add_parent(parent);
    }

    pub fn add_timeout(&self, timeout: Duration) {
        self.cancel.add_timeout(timeout);
    }

    pub fn add_deadline(&self, deadline: Instant) {
        self.cancel.add_deadline(deadline);
    }

    pub fn cancel_handle(&self) -> Cancel {
        self.cancel.clone()
    }

    pub fn cancel(&self) {
        self.guards.close();
        self.cancel.set();
    }

    // Should we really expose the "closed but not cancelled" use case?
    pub fn close(&self) {
        self.guards.close()
    }

    pub fn is_closed(&self) -> bool {
        self.guards.is_closed()
    }

    pub fn len(&self) -> usize {
        self.guards.len()
    }

    pub fn is_empty(&self) -> bool {
        self.guards.is_empty()
    }
}

impl<T> JoinQueue<T>
where
    T: Send + Unpin + 'static,
{
    pub fn push(&self, guard: JoinGuard<T>) -> Result<(), JoinGuard<T>> {
        guard.add_parent(self.cancel.clone());
        self.guards.push_future(guard)
    }

    pub async fn joinable(&self) {
        self.guards.ready().await
    }

    pub async fn join_next(&self) -> Option<JoinGuard<T>> {
        self.guards
            .pop_ready_with_future()
            .await
            .map(|((), guard)| guard)
    }
}

impl<E> JoinQueue<Result<(), E>>
where
    E: Send + Unpin + 'static,
{
    /// Shuts down the remaining tasks gracefully.
    ///
    /// I am not sure about the details yet; for example, how do we merge errors?
    pub async fn shutdown(&self) -> Result<Result<(), E>, ShutdownError> {
        self.shutdown_with_timeout(SHUTDOWN_TIMEOUT).await
    }

    pub async fn shutdown_with_timeout(
        &self,
        timeout: Duration,
    ) -> Result<Result<(), E>, ShutdownError> {
        self.cancel();

        let mut result = Ok(Ok(()));
        tokio::pin! { let sleep = time::sleep(timeout); }
        loop {
            tokio::select! {
                () = &mut sleep => {
                    result = join_guard::merge((result, Err(ShutdownError::JoinTimeout)));
                    break;
                }
                guard = self.join_next() => {
                    let Some(mut guard) = guard else { break };
                    result = join_guard::merge((result, guard.take_result()));
                }
            }
        }

        result
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::future;
    use std::sync::Arc;

    use tokio::time;

    use super::*;

    impl<T> JoinQueue<T> {
        fn assert(&self, closed: bool, len: usize, cancel: bool) {
            assert_eq!(self.is_closed(), closed);
            assert_eq!(self.len(), len);
            assert_eq!(self.is_empty(), len == 0);
            assert_eq!(self.cancel.is_set(), cancel);
        }
    }

    #[tokio::test]
    async fn join_queue() {
        fn spawn(value: u8) -> JoinGuard<u8> {
            JoinGuard::spawn(|cancel| async move {
                cancel.wait().await;
                value
            })
        }

        let queue = Arc::new(JoinQueue::new());
        queue.assert(false, 0, false);

        assert_matches!(queue.push(spawn(1)), Ok(()));
        queue.assert(false, 1, false);

        let guard = spawn(2);
        guard.add_timeout(Duration::ZERO);
        assert_matches!(queue.push(guard), Ok(()));
        queue.assert(false, 2, false);

        let mut guard = queue.join_next().await.unwrap();
        queue.assert(false, 1, false);
        assert_eq!(guard.is_finished(), true);
        assert_eq!(guard.shutdown().await, Ok(2));

        let join_next_task = {
            let queue = queue.clone();
            tokio::spawn(async move { queue.join_next().await })
        };

        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(join_next_task.is_finished(), false);

        queue.cancel();
        let mut guard = join_next_task.await.unwrap().unwrap();
        queue.assert(true, 0, true);
        assert_eq!(guard.is_finished(), true);
        assert_eq!(guard.shutdown().await, Ok(1));

        for _ in 0..3 {
            assert_matches!(queue.join_next().await, None);
        }
    }

    #[test]
    fn cancel_when_drop() {
        let queue = JoinQueue::<()>::new();
        let cancel = queue.cancel_handle();
        assert_eq!(cancel.is_set(), false);

        drop(queue);
        assert_eq!(cancel.is_set(), true);
    }

    #[tokio::test]
    async fn shutdown() {
        async fn test(
            queue: &JoinQueue<Result<(), ()>>,
            expect: Result<Result<(), ()>, ShutdownError>,
            expect_len: usize,
        ) {
            assert_eq!(
                queue.shutdown_with_timeout(Duration::from_millis(10)).await,
                expect,
            );
            assert_eq!(queue.len(), expect_len);
        }

        fn spawn_ok() -> JoinGuard<Result<(), ()>> {
            JoinGuard::spawn(|cancel| async move { Ok(cancel.wait().await) })
        }

        fn spawn_err() -> JoinGuard<Result<(), ()>> {
            JoinGuard::spawn(|cancel| async move { Err(cancel.wait().await) })
        }

        fn spawn_pending() -> JoinGuard<Result<(), ()>> {
            JoinGuard::spawn(|_| future::pending())
        }

        let queue = JoinQueue::new();
        assert_matches!(queue.push(spawn_ok()), Ok(()));
        test(&queue, Ok(Ok(())), 0).await;

        let queue = JoinQueue::new();
        assert_matches!(queue.push(spawn_err()), Ok(()));
        test(&queue, Ok(Err(())), 0).await;

        let queue = JoinQueue::new();
        assert_matches!(queue.push(spawn_ok()), Ok(()));
        assert_matches!(queue.push(spawn_err()), Ok(()));
        test(&queue, Ok(Err(())), 0).await;

        let queue = JoinQueue::new();
        assert_matches!(queue.push(spawn_pending()), Ok(()));
        test(&queue, Err(ShutdownError::JoinTimeout), 1).await;

        let queue = JoinQueue::new();
        assert_matches!(queue.push(spawn_ok()), Ok(()));
        assert_matches!(queue.push(spawn_pending()), Ok(()));
        test(&queue, Err(ShutdownError::JoinTimeout), 1).await;

        let queue = JoinQueue::new();
        assert_matches!(queue.push(spawn_ok()), Ok(()));
        assert_matches!(queue.push(spawn_err()), Ok(()));
        assert_matches!(queue.push(spawn_pending()), Ok(()));
        test(&queue, Ok(Err(())), 1).await;
    }
}
