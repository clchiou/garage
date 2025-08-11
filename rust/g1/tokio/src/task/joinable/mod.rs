pub mod fold;
pub mod join;
pub mod map;
pub mod try_fold;
pub mod try_join;

use std::future::Future;
use std::time::Duration;

use async_trait::async_trait;
use tokio::time::Instant;

use super::join_guard::{Cancel, JoinGuard, SHUTDOWN_TIMEOUT, ShutdownError};

use self::map::Map;

#[async_trait]
pub trait Joinable: Future<Output = ()> {
    type Output;

    fn add_parent(&self, parent: Cancel);

    fn add_timeout(&self, timeout: Duration);

    fn add_deadline(&self, deadline: Instant);

    fn cancel(&self);

    async fn shutdown(&mut self) -> Result<<Self as Joinable>::Output, ShutdownError> {
        self.shutdown_with_timeout(SHUTDOWN_TIMEOUT).await
    }

    async fn shutdown_with_timeout(
        &mut self,
        timeout: Duration,
    ) -> Result<<Self as Joinable>::Output, ShutdownError>;

    fn take_result(&mut self) -> Result<<Self as Joinable>::Output, ShutdownError>;

    fn boxed(self) -> BoxJoinable<<Self as Joinable>::Output>
    where
        Self: Send + Unpin + 'static,
        Self: Sized,
    {
        Box::new(self)
    }

    fn map<U, F>(self, f: F) -> Map<Self, F>
    where
        Self: Sized,
        F: FnOnce(<Self as Joinable>::Output) -> U,
    {
        Map::new(self, f)
    }
}

// Fix the lifetime to `'static` for now, since I cannot think of any non-`'static` use cases.
// TODO: Should we use `Pin<Box<...>>` instead?
pub type BoxJoinable<T> = Box<dyn Joinable<Output = T> + Send + Unpin + 'static>;

#[async_trait]
impl<T> Joinable for JoinGuard<T>
where
    T: Send,
{
    type Output = T;

    fn add_parent(&self, parent: Cancel) {
        self.add_parent(parent)
    }

    fn add_timeout(&self, timeout: Duration) {
        self.add_timeout(timeout)
    }

    fn add_deadline(&self, deadline: Instant) {
        self.add_deadline(deadline)
    }

    fn cancel(&self) {
        self.cancel()
    }

    async fn shutdown_with_timeout(
        &mut self,
        timeout: Duration,
    ) -> Result<<Self as Joinable>::Output, ShutdownError> {
        self.shutdown_with_timeout(timeout).await
    }

    fn take_result(&mut self) -> Result<<Self as Joinable>::Output, ShutdownError> {
        self.take_result()
    }
}

#[async_trait]
impl<T> Joinable for BoxJoinable<T> {
    type Output = T;

    fn add_parent(&self, parent: Cancel) {
        (**self).add_parent(parent)
    }

    fn add_timeout(&self, timeout: Duration) {
        (**self).add_timeout(timeout)
    }

    fn add_deadline(&self, deadline: Instant) {
        (**self).add_deadline(deadline)
    }

    fn cancel(&self) {
        (**self).cancel()
    }

    async fn shutdown_with_timeout(
        &mut self,
        timeout: Duration,
    ) -> Result<<Self as Joinable>::Output, ShutdownError> {
        (**self).shutdown_with_timeout(timeout).await
    }

    fn take_result(&mut self) -> Result<<Self as Joinable>::Output, ShutdownError> {
        (**self).take_result()
    }
}
