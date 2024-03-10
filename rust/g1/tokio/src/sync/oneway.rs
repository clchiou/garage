//! Flag type that cannot be cleared (hence "oneway").

use std::sync::atomic::{AtomicBool, Ordering};

use tokio::sync::Notify;

#[derive(Debug, Default)]
pub struct Flag {
    flag: AtomicBool,
    notify: Notify,
}

impl Flag {
    pub fn new() -> Self {
        Default::default()
    }

    pub fn is_set(&self) -> bool {
        self.flag.load(Ordering::SeqCst)
    }

    pub fn set(&self) {
        self.flag.store(true, Ordering::SeqCst);
        self.notify.notify_waiters();
    }

    pub async fn wait(&self) {
        tokio::pin! { let notified = self.notify.notified(); }
        notified.as_mut().enable();
        if !self.is_set() {
            notified.as_mut().await;
        }
        assert!(self.is_set());
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;
    use std::time::Duration;

    use tokio::time;

    use super::*;

    #[tokio::test]
    async fn flag() {
        let flag = Arc::new(Flag::new());
        assert_eq!(flag.is_set(), false);

        let task_1 = {
            let flag = flag.clone();
            tokio::spawn(async move { flag.wait().await })
        };
        let task_2 = {
            let flag = flag.clone();
            tokio::spawn(async move { flag.wait().await })
        };

        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task_1.is_finished(), false);
        assert_eq!(task_2.is_finished(), false);

        flag.set();
        assert_eq!(flag.is_set(), true);

        assert!(matches!(task_1.await, Ok(())));
        assert!(matches!(task_2.await, Ok(())));

        let task_3 = {
            let flag = flag.clone();
            tokio::spawn(async move { flag.wait().await })
        };
        assert!(matches!(task_3.await, Ok(())));
    }
}
