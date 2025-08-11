use std::future::Future;
use std::pin::Pin;
use std::task::{Context, Poll};
use std::time::Duration;

use async_trait::async_trait;
use tokio::time::Instant;

use crate::task::join_guard::{Cancel, ShutdownError};

use super::Joinable;

#[derive(Debug)]
pub struct Map<J, F> {
    joinable: J,
    f: Option<F>,
}

impl<J, F> Map<J, F> {
    pub(super) fn new(joinable: J, f: F) -> Self {
        Self {
            joinable,
            f: Some(f),
        }
    }
}

impl<J, F> Future for Map<J, F>
where
    J: Joinable,
{
    type Output = ();

    fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
        unsafe { self.map_unchecked_mut(|this| &mut this.joinable) }.poll(context)
    }
}

#[async_trait]
impl<J, F, U> Joinable for Map<J, F>
where
    J: Joinable + Send,
    F: FnOnce(<J as Joinable>::Output) -> U + Send,
{
    type Output = U;

    fn add_parent(&self, parent: Cancel) {
        self.joinable.add_parent(parent)
    }

    fn add_timeout(&self, timeout: Duration) {
        self.joinable.add_timeout(timeout)
    }

    fn add_deadline(&self, deadline: Instant) {
        self.joinable.add_deadline(deadline)
    }

    fn cancel(&self) {
        self.joinable.cancel()
    }

    async fn shutdown_with_timeout(
        &mut self,
        timeout: Duration,
    ) -> Result<<Self as Joinable>::Output, ShutdownError> {
        self.joinable
            .shutdown_with_timeout(timeout)
            .await
            .map(|output| (self.f.take().expect("map"))(output))
    }

    fn take_result(&mut self) -> Result<<Self as Joinable>::Output, ShutdownError> {
        self.joinable
            .take_result()
            .map(|output| (self.f.take().expect("map"))(output))
    }
}
