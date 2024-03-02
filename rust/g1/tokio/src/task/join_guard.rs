use std::error;
use std::fmt;
use std::future::Future;
use std::io;
use std::panic;
use std::pin::Pin;
use std::sync::Arc;
use std::task::{Context, Poll};
use std::time::Duration;

#[cfg(tokio_unstable)]
use tokio::task::Id;
use tokio::{
    task::{JoinError, JoinHandle},
    time::{self, Instant},
};

use crate::sync::oneway::Flag;

/// Scoped `JoinHandle` with cooperative cancellation.
///
/// We do not expose `abort` directly to the user.  Instead, user should just drop the guard.
#[derive(Debug)]
pub struct JoinGuard<T> {
    handle: JoinHandle<T>,
    result: Option<Result<T, JoinError>>,
    cancel: Cancel,
}

#[derive(Clone, Debug)]
pub struct Cancel(Arc<Flag>);

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ShutdownError {
    JoinTimeout,
    // Name it `TaskAborted` to avoid confusion with cooperative cancellation.
    TaskAborted,
}

pub(super) const SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(1);

/// Merge join results.
///
/// I am not sure about the details yet, but for now, the priority is as follows:
/// E > TaskAborted > JoinTimeout > Ok
///
/// TODO: I need a better idea here, but for now, if both `JoinGuard::shutdown` return an error,
/// one of them is silently dropped.
#[allow(clippy::type_complexity)]
pub(super) fn merge<E>(
    join_results: (
        Result<Result<(), E>, ShutdownError>,
        Result<Result<(), E>, ShutdownError>,
    ),
) -> Result<Result<(), E>, ShutdownError> {
    match join_results {
        (result @ Ok(Err(_)), _) => result,
        (_, result @ Ok(Err(_))) => result,

        (result @ Err(ShutdownError::TaskAborted), _) => result,
        (_, result @ Err(ShutdownError::TaskAborted)) => result,

        (result @ Err(ShutdownError::JoinTimeout), _) => result,
        (_, result @ Err(ShutdownError::JoinTimeout)) => result,

        (Ok(Ok(())), Ok(Ok(()))) => Ok(Ok(())),
    }
}

impl<T> JoinGuard<T> {
    pub fn spawn<F>(new_future: impl FnOnce(Cancel) -> F) -> Self
    where
        F: Future<Output = T> + Send + 'static,
        F::Output: Send + 'static,
    {
        let cancel = Cancel::new();
        let handle = tokio::spawn(new_future(cancel.clone()));
        Self::new(handle, cancel)
    }

    pub fn new(handle: JoinHandle<T>, cancel: Cancel) -> Self {
        Self {
            handle,
            result: None,
            cancel,
        }
    }

    pub fn add_parent(&self, parent: Cancel) {
        self.cancel.add_parent(parent);
    }

    pub fn add_timeout(&self, timeout: Duration) {
        self.cancel.add_timeout(timeout);
    }

    pub fn add_deadline(&self, deadline: Instant) {
        self.cancel.add_deadline(deadline);
    }

    #[cfg(tokio_unstable)]
    pub fn id(&self) -> Id {
        self.handle.id()
    }

    pub fn is_finished(&self) -> bool {
        self.handle.is_finished()
    }

    pub fn cancel_handle(&self) -> Cancel {
        self.cancel.clone()
    }

    pub fn cancel(&self) {
        self.cancel.set();
    }

    /// Joins the task.
    ///
    /// It can be called more than once before `shutdown` is called.
    pub async fn join(&mut self) {
        if self.result.is_none() {
            self.result = Some((&mut self.handle).await);
        }
    }

    /// Shuts down the task gracefully.
    ///
    /// NOTE: It can be called only once.
    pub async fn shutdown(&mut self) -> Result<T, ShutdownError> {
        self.shutdown_with_timeout(SHUTDOWN_TIMEOUT).await
    }

    pub async fn shutdown_with_timeout(&mut self, timeout: Duration) -> Result<T, ShutdownError> {
        self.cancel();

        if time::timeout(timeout, self.join()).await.is_err() {
            self.handle.abort();
            return Err(ShutdownError::JoinTimeout);
        }

        self.take_result()
    }

    pub fn take_result(&mut self) -> Result<T, ShutdownError> {
        self.result.take().unwrap().map_err(|join_error| {
            if join_error.is_panic() {
                panic::resume_unwind(join_error.into_panic());
            }
            assert!(join_error.is_cancelled());
            ShutdownError::TaskAborted
        })
    }
}

impl<T> Future for JoinGuard<T>
where
    // TODO: Can we remove this bound?  That way, we will not have to re-implement `join` above.
    T: Unpin,
{
    type Output = ();

    fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
        let this = self.get_mut();
        if this.result.is_some() {
            Poll::Ready(())
        } else {
            Pin::new(&mut this.handle).poll(context).map(|result| {
                this.result = Some(result);
            })
        }
    }
}

impl<T> Drop for JoinGuard<T> {
    fn drop(&mut self) {
        self.handle.abort();
        // It is necessary to call `cancel` here to not only propagate the cancellation to child
        // `JoinGuard`s, but also unblock all `add_parent` tasks.
        self.cancel();
    }
}

impl Default for Cancel {
    fn default() -> Self {
        Self::new()
    }
}

impl Cancel {
    pub fn new() -> Self {
        Self(Arc::new(Flag::new()))
    }

    /// Adds a parent to `self`.
    ///
    /// NOTE: If `self` is created by you, it is your responsibility to ensure that `self.set()` is
    /// eventually called.  Otherwise, the `add_parent` task might keep running indefinitely.
    pub fn add_parent(&self, parent: Cancel) {
        self.propagate_from(async move { parent.wait().await });
    }

    pub fn add_timeout(&self, timeout: Duration) {
        self.propagate_from(time::sleep(timeout));
    }

    pub fn add_deadline(&self, deadline: Instant) {
        self.propagate_from(time::sleep_until(deadline));
    }

    fn propagate_from<F>(&self, source: F)
    where
        F: Future<Output = ()> + Send + 'static,
    {
        let this = self.clone();
        tokio::spawn(async move {
            tokio::select! {
                () = source => this.set(),
                () = this.wait() => {}
            }
        });
    }

    pub fn is_set(&self) -> bool {
        self.0.is_set()
    }

    pub fn set(&self) {
        self.0.set()
    }

    pub async fn wait(&self) {
        self.0.wait().await
    }
}

impl fmt::Display for ShutdownError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:?}", self)
    }
}

impl error::Error for ShutdownError {}

// We implement conversion to `std::io::Error` for convenience.
impl From<ShutdownError> for io::Error {
    fn from(error: ShutdownError) -> Self {
        Self::new(
            match error {
                ShutdownError::JoinTimeout => io::ErrorKind::TimedOut,
                ShutdownError::TaskAborted => io::ErrorKind::Other,
            },
            error,
        )
    }
}

/// Joins `JoinGuard` together in a "join-any-shutdown-all" manner.
///
/// I am not sure about the details yet; for example, how do we merge errors?
#[derive(Debug)]
pub struct JoinAny<E>(JoinGuard<Result<(), E>>, JoinGuard<Result<(), E>>);

impl<E> JoinAny<E> {
    pub fn new(guard0: JoinGuard<Result<(), E>>, guard1: JoinGuard<Result<(), E>>) -> Self {
        Self(guard0, guard1)
    }

    pub fn add_parent(&self, parent: Cancel) {
        self.0.add_parent(parent.clone());
        self.1.add_parent(parent);
    }

    pub fn add_timeout(&self, timeout: Duration) {
        self.0.add_timeout(timeout);
        self.1.add_timeout(timeout);
    }

    pub fn add_deadline(&self, deadline: Instant) {
        self.0.add_deadline(deadline);
        self.1.add_deadline(deadline);
    }

    pub fn cancel(&self) {
        self.0.cancel();
        self.1.cancel();
    }

    /// Returns when any `JoinGuard::join` returns.
    pub async fn join(&mut self) {
        tokio::select! {
            () = self.0.join() => {}
            () = self.1.join() => {}
        }
    }

    /// Shuts down all `JoinGuard`.
    pub async fn shutdown(&mut self) -> Result<Result<(), E>, ShutdownError> {
        merge(tokio::join!(self.0.shutdown(), self.1.shutdown()))
    }
}

#[cfg(test)]
mod tests {
    use std::future;
    use std::sync::{Arc, Mutex};

    use g1_base::sync::MutexExt;

    use super::*;

    fn spawn_tasks() -> (JoinGuard<()>, Arc<Mutex<Vec<&'static str>>>) {
        let mock = Arc::new(Mutex::new(Vec::new()));
        let parent = {
            let mock = mock.clone();
            JoinGuard::spawn(|cancel_parent| async move {
                scopeguard::defer! {
                    mock.must_lock().push("parent");
                }

                let mut child = {
                    let mock = mock.clone();
                    JoinGuard::spawn(|cancel_child| async move {
                        scopeguard::defer! {
                            mock.must_lock().push("child");
                        }

                        cancel_child.wait().await;
                    })
                };
                child.add_parent(cancel_parent.clone());

                tokio::join!(cancel_parent.wait(), child.join());
            })
        };
        (parent, mock)
    }

    #[tokio::test]
    async fn add_parent() {
        let (mut parent, mock) = spawn_tasks();
        parent.cancel();
        for _ in 0..3 {
            parent.join().await;
            assert!(matches!(parent.result, Some(Ok(()))));
        }
        assert_eq!(*mock.must_lock(), ["child", "parent"]);
    }

    #[tokio::test]
    async fn add_parent_deep() {
        let mut guards = Vec::<JoinGuard<_>>::new();
        for depth in 0..20 {
            let guard = JoinGuard::spawn(|cancel| async move {
                cancel.wait().await;
                depth
            });
            if let Some(last) = guards.last() {
                guard.add_parent(last.cancel_handle());
            }
            guards.push(guard);
        }

        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        for guard in guards.iter() {
            assert_eq!(guard.is_finished(), false);
        }

        guards[0].cancel();
        for (depth, guard) in guards.iter_mut().enumerate() {
            guard.join().await;
            assert_eq!(guard.take_result(), Ok(depth));
        }
    }

    #[tokio::test]
    async fn add_timeout() {
        let mut guard = JoinGuard::spawn(|cancel| async move { cancel.wait().await });
        guard.add_timeout(Duration::ZERO);
        for _ in 0..3 {
            guard.join().await;
            assert!(matches!(guard.result, Some(Ok(()))));
        }
    }

    #[tokio::test]
    async fn add_deadline() {
        let mut guard = JoinGuard::spawn(|cancel| async move { cancel.wait().await });
        guard.add_deadline(Instant::now());
        for _ in 0..3 {
            guard.join().await;
            assert!(matches!(guard.result, Some(Ok(()))));
        }
    }

    #[tokio::test]
    async fn join() {
        let mut guard = JoinGuard::spawn(|_| async { 42 });
        assert!(matches!(guard.result, None));
        assert_eq!(guard.join().await, ());
        assert!(matches!(guard.result, Some(Ok(42))));

        let mut guard = JoinGuard::spawn(|_| async { 42 });
        assert!(matches!(guard.result, None));
        assert_eq!((&mut guard).await, ());
        assert!(matches!(guard.result, Some(Ok(42))));
    }

    #[tokio::test]
    async fn shutdown() {
        let (mut parent, mock) = spawn_tasks();
        assert_eq!(parent.shutdown().await, Ok(()));
        assert_eq!(*mock.must_lock(), ["child", "parent"]);

        let mut guard = JoinGuard::spawn(|_| future::pending::<()>());
        assert_eq!(
            guard.shutdown_with_timeout(Duration::ZERO).await,
            Err(ShutdownError::JoinTimeout),
        );
        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(guard.is_finished(), true);

        let mut guard = JoinGuard::spawn(|_| future::pending::<()>());
        guard.handle.abort();
        assert_eq!(guard.shutdown().await, Err(ShutdownError::TaskAborted));
    }

    #[tokio::test]
    async fn guard() {
        let (parent, mock) = spawn_tasks();
        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        drop(parent);
        time::sleep(Duration::from_millis(10)).await;
        {
            let mut mock = mock.must_lock();
            mock.sort();
            assert_eq!(*mock, ["child", "parent"]);
            mock.clear();
        }

        let guard = {
            let mock = mock.clone();
            JoinGuard::spawn(|_| async move {
                scopeguard::defer! {
                    mock.must_lock().push("guard");
                }

                future::pending::<()>().await;
            })
        };
        time::sleep(Duration::from_millis(10)).await;
        drop(guard);
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(*mock.must_lock(), ["guard"]);
    }

    #[test]
    fn test_merge() {
        fn test(
            r0: Result<Result<(), &str>, ShutdownError>,
            r1: Result<Result<(), &str>, ShutdownError>,
            expect: Result<Result<(), &str>, ShutdownError>,
        ) {
            assert_eq!(merge((r0.clone(), r1.clone())), expect);
            assert_eq!(merge((r1, r0)), expect);
        }

        assert_eq!(merge((Ok(Err("foo")), Ok(Err("bar")))), Ok(Err("foo")));
        test(
            Ok(Err("foo")),
            Err(ShutdownError::TaskAborted),
            Ok(Err("foo")),
        );
        test(
            Ok(Err("foo")),
            Err(ShutdownError::JoinTimeout),
            Ok(Err("foo")),
        );
        test(Ok(Err("foo")), Ok(Ok(())), Ok(Err("foo")));

        test(
            Err(ShutdownError::TaskAborted),
            Err(ShutdownError::TaskAborted),
            Err(ShutdownError::TaskAborted),
        );
        test(
            Err(ShutdownError::TaskAborted),
            Err(ShutdownError::JoinTimeout),
            Err(ShutdownError::TaskAborted),
        );
        test(
            Err(ShutdownError::TaskAborted),
            Ok(Ok(())),
            Err(ShutdownError::TaskAborted),
        );

        test(
            Err(ShutdownError::JoinTimeout),
            Err(ShutdownError::JoinTimeout),
            Err(ShutdownError::JoinTimeout),
        );
        test(
            Err(ShutdownError::JoinTimeout),
            Ok(Ok(())),
            Err(ShutdownError::JoinTimeout),
        );

        test(Ok(Ok(())), Ok(Ok(())), Ok(Ok(())));
    }
}
