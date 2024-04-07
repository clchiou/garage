use std::sync::Mutex;
use std::task::{Context, Poll, Waker};

use crate::sync::MutexExt;

pub trait PollExt<T> {
    // Why does the stdlib not provide this?
    fn inspect<F>(self, f: F) -> Self
    where
        F: FnOnce(&T);
}

impl<T> PollExt<T> for Poll<T> {
    fn inspect<F>(self, f: F) -> Self
    where
        F: FnOnce(&T),
    {
        if let Poll::Ready(x) = &self {
            f(x);
        }
        self
    }
}

/// Stores the most recent `Waker` of a task.
#[derive(Debug, Default)]
pub struct WakerCell(Mutex<Option<Waker>>);

impl WakerCell {
    pub fn new() -> Self {
        Self(Mutex::new(None))
    }

    pub fn update(&self, context: &mut Context) {
        update_waker(&mut self.0.must_lock(), context);
    }

    pub fn wake(&self) {
        if let Some(waker) = self.0.must_lock().take() {
            waker.wake();
        }
    }

    pub fn clear(&self) {
        *self.0.must_lock() = None;
    }
}

pub fn update_waker(waker: &mut Option<Waker>, context: &Context) {
    let new_waker = context.waker();
    match waker {
        // The [doc] recommends using `clone_from`.
        //
        // [doc]: https://doc.rust-lang.org/std/task/struct.Waker.html
        Some(waker) => waker.clone_from(new_waker),
        None => *waker = Some(new_waker.clone()),
    }
}
