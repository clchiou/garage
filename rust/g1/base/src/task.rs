use std::sync::Mutex;
use std::task::{Context, Waker};

use crate::sync::MutexExt;

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
    let should_update = match waker.as_ref() {
        Some(old_waker) => !new_waker.will_wake(old_waker),
        None => true,
    };
    if should_update {
        *waker = Some(new_waker.clone());
    }
}
