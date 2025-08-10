use std::error;
use std::fmt;
use std::future::Future;
use std::io;
use std::mem;
use std::panic;
use std::pin::Pin;
use std::sync::Arc;
use std::task::{self, Context, Poll};
use std::time::Duration;

#[cfg(tokio_unstable)]
use tokio::task::Id;
use tokio::task::{JoinError, JoinHandle};
use tokio::time::{self, Instant};

use crate::sync::oneway::Flag;

/// Scoped `JoinHandle` with cooperative cancellation.
///
/// We do not expose `abort` directly to the user.  Instead, user should just drop the guard.
#[derive(Debug)]
pub struct JoinGuard<T> {
    stage: Stage<T>,
    cancel: Cancel,
    #[cfg(tokio_unstable)]
    id: Id,
}

#[derive(Debug)]
enum Stage<T> {
    Running(JoinHandle<T>),
    Finished(Result<T, JoinError>),
    Consumed,
}

#[derive(Clone, Debug, Default)]
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
        #[cfg(tokio_unstable)]
        let id = handle.id();
        Self {
            stage: Stage::Running(handle),
            cancel,
            #[cfg(tokio_unstable)]
            id,
        }
    }

    fn handle(&self) -> Option<&JoinHandle<T>> {
        match &self.stage {
            Stage::Running(handle) => Some(handle),
            _ => None,
        }
    }

    fn handle_mut(&mut self) -> Option<&mut JoinHandle<T>> {
        match &mut self.stage {
            Stage::Running(handle) => Some(handle),
            _ => None,
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
        self.id
    }

    pub fn is_finished(&self) -> bool {
        self.handle().is_none_or(|handle| handle.is_finished())
    }

    fn abort(&self) {
        if let Some(handle) = self.handle() {
            handle.abort();
        }
    }

    pub fn cancel_handle(&self) -> Cancel {
        self.cancel.clone()
    }

    pub fn cancel(&self) {
        self.cancel.set();
    }

    /// Shuts down the task gracefully.
    ///
    /// NOTE: It can be called only once.
    pub async fn shutdown(&mut self) -> Result<T, ShutdownError> {
        self.shutdown_with_timeout(SHUTDOWN_TIMEOUT).await
    }

    pub async fn shutdown_with_timeout(&mut self, timeout: Duration) -> Result<T, ShutdownError> {
        self.cancel();

        if time::timeout(timeout, &mut *self).await.is_err() {
            self.abort();
            return Err(ShutdownError::JoinTimeout);
        }

        self.take_result()
    }

    pub fn take_result(&mut self) -> Result<T, ShutdownError> {
        match mem::replace(&mut self.stage, Stage::Consumed) {
            Stage::Running(handle) => {
                handle.abort();
                panic!("task is still running; abort")
            }
            Stage::Finished(result) => result,
            Stage::Consumed => panic!("task result was consumed"),
        }
        .map_err(|join_error| {
            if join_error.is_panic() {
                panic::resume_unwind(join_error.into_panic());
            }
            assert!(join_error.is_cancelled());
            ShutdownError::TaskAborted
        })
    }

    pub fn checked_take_result(&mut self) -> Option<Result<T, ShutdownError>> {
        matches!(self.stage, Stage::Finished(_)).then(|| self.take_result())
    }
}

// TODO: I cannot prove this, but I feel it is correct.
impl<T> Unpin for JoinGuard<T> {}

impl<T> Future for JoinGuard<T> {
    type Output = ();

    fn poll(mut self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
        if let Some(handle) = self.handle_mut() {
            self.stage = Stage::Finished(task::ready!(Pin::new(handle).poll(context)));
        }
        Poll::Ready(())
    }
}

impl<T> Drop for JoinGuard<T> {
    fn drop(&mut self) {
        self.abort();
        // It is necessary to call `cancel` here to not only propagate the cancellation to child
        // `JoinGuard`s, but also unblock all `add_parent` tasks.
        self.cancel();
    }
}

impl Cancel {
    pub fn new() -> Self {
        Default::default()
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
        write!(f, "{self:?}")
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

                let child = {
                    let mock = mock.clone();
                    JoinGuard::spawn(|cancel_child| async move {
                        scopeguard::defer! {
                            mock.must_lock().push("child");
                        }

                        cancel_child.wait().await;
                    })
                };
                child.add_parent(cancel_parent.clone());

                tokio::join!(cancel_parent.wait(), child);
            })
        };
        (parent, mock)
    }

    #[tokio::test]
    async fn add_parent() {
        let (mut parent, mock) = spawn_tasks();
        parent.cancel();
        for _ in 0..3 {
            (&mut parent).await;
            assert!(matches!(parent.stage, Stage::Finished(Ok(()))));
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
        for (depth, mut guard) in guards.iter_mut().enumerate() {
            (&mut guard).await;
            assert_eq!(guard.take_result(), Ok(depth));
        }
    }

    #[tokio::test]
    async fn add_timeout() {
        let mut guard = JoinGuard::spawn(|cancel| async move { cancel.wait().await });
        guard.add_timeout(Duration::ZERO);
        for _ in 0..3 {
            (&mut guard).await;
            assert!(matches!(guard.stage, Stage::Finished(Ok(()))));
        }
    }

    #[tokio::test]
    async fn add_deadline() {
        let mut guard = JoinGuard::spawn(|cancel| async move { cancel.wait().await });
        guard.add_deadline(Instant::now());
        for _ in 0..3 {
            (&mut guard).await;
            assert!(matches!(guard.stage, Stage::Finished(Ok(()))));
        }
    }

    #[tokio::test]
    async fn join() {
        let mut guard = JoinGuard::spawn(|_| async { 42 });
        assert!(matches!(guard.stage, Stage::Running(_)));
        assert_eq!((&mut guard).await, ());
        assert!(matches!(guard.stage, Stage::Finished(Ok(42))));
        assert!(matches!(guard.take_result(), Ok(42)));
        assert!(matches!(guard.stage, Stage::Consumed));
        for _ in 0..3 {
            assert_eq!((&mut guard).await, ());
            assert!(matches!(guard.stage, Stage::Consumed));
        }
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
        guard.abort();
        assert_eq!(guard.shutdown().await, Err(ShutdownError::TaskAborted));
    }

    #[tokio::test]
    #[should_panic(expected = "task is still running; abort")]
    async fn take_result_running() {
        let mut guard = JoinGuard::spawn(|_| future::pending::<()>());
        let _ = guard.take_result();
    }

    #[tokio::test]
    #[should_panic(expected = "task result was consumed")]
    async fn take_result_consumed() {
        let mut guard = JoinGuard::spawn(|_| async { 42 });
        (&mut guard).await;
        assert!(matches!(guard.take_result(), Ok(42)));
        let _ = guard.take_result();
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
