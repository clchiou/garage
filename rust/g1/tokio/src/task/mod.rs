mod join_queue;
mod joiner;

use std::panic;
use std::time::Duration;

use tokio::{sync::Mutex, task::JoinHandle, time};

pub use join_queue::JoinQueue;
pub use joiner::Joiner;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum JoinTaskError {
    Cancelled,
    Timeout,
}

pub async fn join_task<T>(
    task: &Mutex<JoinHandle<T>>,
    timeout: Duration,
) -> Result<T, JoinTaskError> {
    let join_result = {
        let mut task = task.lock().await;
        match time::timeout(timeout, &mut *task).await {
            Ok(join_result) => join_result,
            Err(_) => {
                task.abort();
                return Err(JoinTaskError::Timeout);
            }
        }
    };
    match join_result {
        Ok(result) => Ok(result),
        Err(join_error) => {
            if join_error.is_panic() {
                panic::resume_unwind(join_error.into_panic());
            }
            assert!(join_error.is_cancelled());
            Err(JoinTaskError::Cancelled)
        }
    }
}
