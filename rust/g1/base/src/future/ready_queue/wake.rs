use std::sync::{Arc, Mutex, Weak};
use std::task::Wake;

use crate::sync::MutexExt;

use super::queue::{Id, Queue};

/// Transitions a future from the `pending` state to the `polling` state.
#[derive(Debug)]
pub(super) struct FutureWaker<T, Fut> {
    // I am not sure if there is a circular reference, but using a weak reference is probably
    // harmless anyway.
    queue: Weak<Mutex<Queue<T, Fut>>>,
    id: Id,
}

impl<T, Fut> FutureWaker<T, Fut> {
    pub(super) fn new(queue: Weak<Mutex<Queue<T, Fut>>>, id: Id) -> Self {
        Self { queue, id }
    }
}

impl<T, Fut> Wake for FutureWaker<T, Fut> {
    fn wake(self: Arc<Self>) {
        Self::wake_by_ref(&self);
    }

    fn wake_by_ref(self: &Arc<Self>) {
        // If `ReadyQueue` is dropped before the waker gets called, I guess we should just do
        // nothing.  It is possible that the waker lives longer than its future.
        if let Some(queue) = self.queue.upgrade() {
            queue.must_lock().resume_polling(self.id);
        }
    }
}
