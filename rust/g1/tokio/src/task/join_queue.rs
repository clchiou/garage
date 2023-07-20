use std::future::Future;
use std::panic;

#[cfg(tokio_unstable)]
use tokio::task::Id;
use tokio::task::{AbortHandle, JoinError, JoinHandle};

use g1_base::future::ReadyQueue;

// `JoinQueue::clone` is shallow, not deep.  This is the opposite of ordinary collection types.
// We keep it shallow to facilitate sharing among threads.
#[derive(Clone, Debug)]
pub struct JoinQueue<T>(ReadyQueue<Result<T, JoinError>, JoinHandle<T>>);

impl<T> Default for JoinQueue<T> {
    fn default() -> Self {
        Self::new()
    }
}

impl<T> JoinQueue<T> {
    pub fn new() -> Self {
        Self(ReadyQueue::new())
    }

    pub fn close(&self) {
        self.0.close();
    }

    pub fn is_closed(&self) -> bool {
        self.0.is_closed()
    }

    pub fn len(&self) -> usize {
        self.0.len()
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }
}

impl<T> JoinQueue<T>
where
    T: Send + 'static,
{
    pub fn spawn<F>(&self, task: F) -> Result<AbortHandle, JoinHandle<T>>
    where
        F: Future<Output = T> + Send + 'static,
    {
        let handle = tokio::spawn(task);
        let abort_handle = handle.abort_handle();
        self.0.push_future(handle)?;
        Ok(abort_handle)
    }

    pub async fn join_next(&self) -> Option<Result<T, JoinError>> {
        self.0.pop_ready().await
    }

    #[cfg(tokio_unstable)]
    pub async fn join_next_with_id(&self) -> Option<Result<(Id, T), JoinError>> {
        self.0
            .pop_ready_with_future()
            .await
            .map(|(result, handle)| result.map(|value| (handle.id(), value)))
    }

    pub async fn abort_all_then_join(&self) {
        async fn abort_all_then_join_impl<T>(this: &JoinQueue<T>) {
            let handles = this.0.detach_all();
            for handle in &handles {
                handle.abort();
            }
            for handle in handles {
                resume_panic(handle.await);
            }
            while let Some(join_result) = this.0.try_pop_ready() {
                resume_panic(join_result);
            }
        }

        self.0.close();
        abort_all_then_join_impl(self).await;
        // `ReadyQueue::detach_all` has an idiosyncrasy: if it is called while `pop_ready` is
        // executing, the future that is currently being polled by `pop_ready` will not be returned
        // by `detach_all`.  In this case, we call `detach_all` again and hope that we are lucky
        // enough that the future is not being polled this time.
        //
        // TODO: Figure out how to handle this corner case that does not rely on luck.
        if !self.0.is_empty() {
            assert_eq!(self.0.len(), 1);
            abort_all_then_join_impl(self).await;
            assert!(self.0.is_empty());
        }
    }

    /// Aborts all tasks.
    ///
    /// NOTE: Unlike `tokio::task::JoinSet::abort_all`, this method removes all tasks from the
    /// queue.
    // TODO: Consider changing this method to avoid removing tasks from the queue.
    pub fn abort_all(&self) {
        fn abort_all_impl<T>(this: &JoinQueue<T>) {
            let handles = this.0.detach_all();
            for handle in &handles {
                handle.abort();
            }
            while this.0.try_pop_ready().is_some() {
                // Do nothing here.
            }
        }

        self.0.close();
        abort_all_impl(self);
        // Ditto.
        if !self.0.is_empty() {
            assert_eq!(self.0.len(), 1);
            abort_all_impl(self);
            assert!(self.0.is_empty());
        }
    }
}

fn resume_panic<T>(join_result: Result<T, JoinError>) {
    if let Err(join_error) = join_result {
        if join_error.is_panic() {
            panic::resume_unwind(join_error.into_panic());
        }
        assert!(join_error.is_cancelled());
    }
}

#[cfg(test)]
mod tests {
    use std::future;
    use std::time::Duration;

    use tokio::time;

    use super::*;

    fn assert_queue<T>(queue: &JoinQueue<T>, is_closed: bool, len: usize) {
        assert_eq!(queue.is_closed(), is_closed);
        assert_eq!(queue.len(), len);
        assert_eq!(queue.is_empty(), len == 0);
    }

    #[tokio::test]
    async fn abort_all_then_join() {
        let queue = JoinQueue::<()>::new();
        let abort_handle = queue.spawn(future::pending()).unwrap();
        assert_queue(&queue, false, 1);

        let join_next_task = {
            let queue = queue.clone();
            tokio::spawn(async move { queue.join_next().await })
        };
        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(abort_handle.is_finished(), false);
        assert_eq!(join_next_task.is_finished(), false);

        queue.abort_all_then_join().await;
        assert_queue(&queue, true, 0);

        assert_eq!(abort_handle.is_finished(), true);
        assert!(matches!(join_next_task.await, Ok(None)));
    }

    #[tokio::test]
    #[should_panic(expected = "test panic")]
    async fn abort_all_then_join_panic() {
        let queue = JoinQueue::new();
        assert!(matches!(queue.spawn(async { panic!("test panic") }), Ok(_)));
        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        queue.abort_all_then_join().await;
    }

    #[tokio::test]
    async fn abort_all() {
        let queue = JoinQueue::<()>::new();
        let abort_handle = queue.spawn(future::pending()).unwrap();
        assert_queue(&queue, false, 1);

        let join_next_task = {
            let queue = queue.clone();
            tokio::spawn(async move { queue.join_next().await })
        };
        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(abort_handle.is_finished(), false);
        assert_eq!(join_next_task.is_finished(), false);

        queue.abort_all();
        assert_queue(&queue, true, 0);

        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(abort_handle.is_finished(), true);
        assert!(matches!(join_next_task.await, Ok(None)));
    }
}
