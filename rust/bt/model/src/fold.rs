//
// A fundamental limitation of the broadcast channel is that the senders are non-blocking.  As a
// result, the channel is leaky - otherwise, the queue length would grow unboundedly.  However, we
// can practically eliminate this leak in the special case where the model updates can be folded
// into a bounded value.
//

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use snafu::prelude::*;
use tokio::sync::Notify;
use tokio::sync::broadcast::error::{RecvError, TryRecvError};

use g1_base::sync::MutexExt;
use g1_tokio::task::{Cancel, JoinGuard};

use crate::{ModelUpdate, ModelUpdateRecv};

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("model update fold closed"))]
pub struct Closed;

pub trait Fold {
    type Value: Sized;

    fn fold(&mut self, value: &mut Option<Self::Value>, update: ModelUpdate);
}

struct FoldActor<F>
where
    F: Fold,
{
    shared: Arc<Shared<F::Value>>,
    model_update_recv: ModelUpdateRecv,
    fold: F,
}

#[derive(Clone, Debug)]
pub struct Consumer<T>(Arc<Shared<T>>);

#[derive(Debug)]
struct Shared<T> {
    value: Mutex<Option<T>>,
    closed: AtomicBool,
    notify: Notify,
}

pub type FoldGuard = JoinGuard<()>;

pub fn spawn<F>(fold: F, model_update_recv: ModelUpdateRecv) -> (Consumer<F::Value>, FoldGuard)
where
    F: Fold + Send + 'static,
    <F as Fold>::Value: Send,
{
    let shared = Arc::new(Shared {
        value: Mutex::new(None),
        closed: AtomicBool::new(false),
        notify: Notify::new(),
    });
    let actor = FoldActor {
        shared: shared.clone(),
        model_update_recv,
        fold,
    };
    (
        Consumer(shared),
        FoldGuard::spawn(|cancel| actor.run(cancel)),
    )
}

impl<F> Drop for FoldActor<F>
where
    F: Fold,
{
    fn drop(&mut self) {
        self.shared.closed.store(true, Ordering::SeqCst);
        self.shared.notify.notify_waiters();
    }
}

impl<F> FoldActor<F>
where
    F: Fold,
{
    async fn run(mut self, cancel: Cancel) {
        tokio::select! {
            () = cancel.wait() => {}
            () = self.fold() => {}
        }
    }

    async fn fold(&mut self) {
        loop {
            match self.model_update_recv.recv().await {
                Ok(update) => {
                    if self.fold_opportunistically(update) {
                        self.shared.notify.notify_one();
                    }
                }
                // The most likely cause of this error is that `self.fold.fold()` is effectively
                // blocking or there was an instantaneous burst of updates.
                Err(RecvError::Lagged(lag)) => {
                    panic!("model update fold is lagging behind: lag={lag}");
                }
                Err(RecvError::Closed) => break,
            }
        }
    }

    fn fold_opportunistically(&mut self, update: ModelUpdate) -> bool {
        let mut value = self.shared.value.must_lock();
        self.fold.fold(&mut value, update);
        loop {
            match self.model_update_recv.try_recv() {
                Ok(update) => self.fold.fold(&mut value, update),
                // Ditto.
                Err(TryRecvError::Lagged(lag)) => {
                    panic!("model update fold is lagging behind: lag={lag}");
                }
                Err(TryRecvError::Empty) | Err(TryRecvError::Closed) => break,
            }
        }
        value.is_some()
    }
}

impl<T> Consumer<T> {
    pub async fn consume(&self) -> Result<T, Closed> {
        tokio::pin! {
            let notify = self.0.notify.notified();
        }
        loop {
            notify.as_mut().enable();
            if let Some(result) = self.try_consume().transpose() {
                return result;
            }
            notify.as_mut().await;
            notify.set(self.0.notify.notified());
        }
    }

    pub fn try_consume(&self) -> Result<Option<T>, Closed> {
        let value = self.0.value.must_lock().take();
        if value.is_none() && self.0.closed.load(Ordering::SeqCst) {
            Err(Closed)
        } else {
            Ok(value)
        }
    }
}
