use std::future::Future;
use std::io::Error;
use std::sync::Arc;

use futures::future::FutureExt;
use tokio::sync::watch::{self, Sender};

use g1_tokio::task::JoinQueue;

#[derive(Debug)]
pub(crate) struct TaskQueue {
    tasks: JoinQueue<Result<(), Error>>,
    any_exit_send: Arc<Sender<bool>>,
}

impl TaskQueue {
    pub(crate) fn new() -> Self {
        let (any_exit_send, _) = watch::channel(false);
        Self {
            tasks: JoinQueue::new(),
            any_exit_send: Arc::new(any_exit_send),
        }
    }

    pub(crate) fn spawn<F>(&self, task: F)
    where
        F: Future<Output = Result<(), Error>> + Send + 'static,
    {
        let any_exit_send = self.any_exit_send.clone();
        self.tasks
            .spawn(task.inspect(move |_| {
                any_exit_send.send_replace(true);
            }))
            .unwrap();
    }

    pub(crate) async fn join_any(&self) {
        let _ = self
            .any_exit_send
            .subscribe()
            .wait_for(|any_exit| *any_exit)
            .await;
    }

    pub(crate) async fn abort_all_then_join(&self) {
        self.tasks.abort_all_then_join().await;
    }
}

impl Drop for TaskQueue {
    fn drop(&mut self) {
        self.tasks.abort_all();
    }
}
