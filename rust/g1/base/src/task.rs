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
        let mut waker = self.0.must_lock();
        let new_waker = context.waker();
        let should_update = match waker.as_ref() {
            Some(old_waker) => !new_waker.will_wake(old_waker),
            None => true,
        };
        if should_update {
            *waker = Some(new_waker.clone());
        }
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
