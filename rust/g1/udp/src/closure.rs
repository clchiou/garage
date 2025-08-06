use std::sync::atomic::{AtomicBool, Ordering};
use std::task::Waker;

use futures::task::AtomicWaker;

#[derive(Debug)]
pub(crate) struct Closure {
    closed: AtomicBool,
    waker: AtomicWaker,
}

impl Closure {
    pub(crate) fn new() -> Self {
        Self {
            closed: AtomicBool::new(false),
            waker: AtomicWaker::new(),
        }
    }

    pub(crate) fn register(&self, waker: &Waker) {
        self.waker.register(waker);
    }

    pub(crate) fn get(&self) -> bool {
        // TODO: Should we use `Ordering::Relaxed` instead?
        self.closed.load(Ordering::SeqCst)
    }

    pub(crate) fn set(&self) {
        // TODO: Should we use `Ordering::Relaxed` instead?
        self.closed.store(true, Ordering::SeqCst);
        self.waker.wake();
    }
}
