use std::sync::{Arc, Mutex, Weak};
use std::task::Wake;

use crate::sync::MutexExt;

use super::impls::{Id, ReadyQueueImpl};

#[derive(Debug)]
pub(super) struct FutureWaker<T, F> {
    // I am not sure if there is a circular reference, but using a weak reference is probably
    // harmless anyway.
    queue: Weak<Mutex<ReadyQueueImpl<T, F>>>,
    id: Id,
}

impl<T, F> FutureWaker<T, F> {
    pub(super) fn new(queue: Weak<Mutex<ReadyQueueImpl<T, F>>>, id: Id) -> Self {
        Self { queue, id }
    }
}

impl<T, F> Wake for FutureWaker<T, F> {
    fn wake(self: Arc<Self>) {
        Self::wake_by_ref(&self);
    }

    fn wake_by_ref(self: &Arc<Self>) {
        // If `ReadyQueue` is dropped before the waker gets called, I guess we should just do
        // nothing.  It is possible that the waker lives longer than its future.
        if let Some(queue) = self.queue.upgrade() {
            let mut queue = queue.must_lock();
            queue.move_to_polling(self.id);
            ReadyQueueImpl::wake(queue);
        }
    }
}
