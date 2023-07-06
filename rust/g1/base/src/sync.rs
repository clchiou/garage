use std::sync::{Mutex, MutexGuard};

pub trait MutexExt<T> {
    // TODO: I am not sure what we should do when a mutex is poisoned.  For now, we just crash.
    // Should I ignore it like `tokio`?
    fn must_lock(&self) -> MutexGuard<'_, T>;
}

impl<T> MutexExt<T> for Mutex<T> {
    fn must_lock(&self) -> MutexGuard<'_, T> {
        self.lock().unwrap()
    }
}
