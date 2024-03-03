use std::future::Future;
use std::pin::Pin;
use std::task::{Context, Poll};
use std::time::Duration;

use tokio::time::{self, Instant};

use g1_base::future::ReadyArray;

use super::join_guard::{self, Cancel, JoinGuard, ShutdownError, SHUTDOWN_TIMEOUT};

#[derive(Debug)]
pub struct JoinArray<T: Unpin, const N: usize>(ReadyArray<JoinCell<T>, N>);

#[derive(Debug)]
struct JoinCell<T>(Option<JoinGuard<T>>);

impl<T, const N: usize> JoinArray<T, N>
where
    T: Unpin,
{
    pub fn new(guards: [JoinGuard<T>; N]) -> Self {
        Self(ReadyArray::new(guards.map(|guard| JoinCell(Some(guard)))))
    }

    pub fn with_cancel(guards: [JoinGuard<T>; N], cancel: Cancel) -> Self {
        for guard in &guards {
            guard.add_parent(cancel.clone());
        }
        Self::new(guards)
    }

    fn for_each<F>(&self, f: F)
    where
        F: FnMut(&JoinGuard<T>),
    {
        self.0.iter().filter_map(|cell| cell.0.as_ref()).for_each(f);
    }

    pub fn add_parent(&self, parent: Cancel) {
        self.for_each(move |guard| guard.add_parent(parent.clone()));
    }

    pub fn add_timeout(&self, timeout: Duration) {
        self.for_each(move |guard| guard.add_timeout(timeout));
    }

    pub fn add_deadline(&self, deadline: Instant) {
        self.for_each(move |guard| guard.add_deadline(deadline));
    }

    pub fn cancel(&self) {
        self.for_each(|guard| guard.cancel());
    }

    pub async fn joinable(&mut self) {
        self.0.ready().await
    }

    pub async fn join_next(&mut self) -> Option<JoinGuard<T>> {
        self.0.pop_ready().await
    }
}

impl<T> Future for JoinCell<T>
where
    T: Unpin,
{
    type Output = JoinGuard<T>;

    fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
        let this = self.get_mut();
        Pin::new(this.0.as_mut().unwrap())
            .poll(context)
            .map(|()| this.0.take().unwrap())
    }
}

impl<E, const N: usize> JoinArray<Result<(), E>, N>
where
    E: Unpin,
{
    /// Shuts down the remaining tasks gracefully.
    ///
    /// I am not sure about the details yet; for example, how do we merge errors?
    pub async fn shutdown(&mut self) -> Result<Result<(), E>, ShutdownError> {
        self.shutdown_with_timeout(SHUTDOWN_TIMEOUT).await
    }

    pub async fn shutdown_with_timeout(
        &mut self,
        timeout: Duration,
    ) -> Result<Result<(), E>, ShutdownError> {
        self.cancel();

        let mut result = Ok(Ok(()));
        tokio::pin! { let sleep = time::sleep(timeout); }
        loop {
            tokio::select! {
                () = &mut sleep => {
                    result = join_guard::merge((result, Err(ShutdownError::JoinTimeout)));
                    break;
                }
                guard = self.join_next() => {
                    let Some(mut guard) = guard else { break };
                    result = join_guard::merge((result, guard.take_result()));
                }
            }
        }

        result
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::future;

    use super::*;

    #[tokio::test]
    async fn cancel_when_drop() {
        let guard = JoinGuard::spawn(|_| future::pending::<()>());
        let cancel = guard.cancel_handle();
        let array = JoinArray::new([guard]);
        assert_eq!(cancel.is_set(), false);

        drop(array);
        assert_eq!(cancel.is_set(), true);
    }

    #[tokio::test]
    async fn joinable() {
        let mut array = JoinArray::new([
            JoinGuard::spawn(|cancel| async move { cancel.wait().await }),
            JoinGuard::spawn(|_| future::pending()),
            JoinGuard::spawn(|_| future::pending()),
        ]);

        // TODO: Can we write this test without using `time::sleep`?
        tokio::select! {
            () = time::sleep(Duration::from_millis(10)) => {}
            () = array.joinable() => std::panic!(),
        }

        array.cancel();

        for _ in 0..3 {
            assert_eq!(array.joinable().await, ());
        }
    }

    #[tokio::test]
    async fn join_next() {
        fn spawn(value: u8) -> JoinGuard<u8> {
            JoinGuard::spawn(|cancel| async move {
                cancel.wait().await;
                value
            })
        }

        let mut array = JoinArray::new([spawn(100), spawn(101), spawn(102)]);

        // TODO: Can we write this test without using `time::sleep`?
        tokio::select! {
            () = time::sleep(Duration::from_millis(10)) => {}
            _ = array.join_next() => std::panic!(),
        }

        array.cancel();

        let mut outputs = [
            array.join_next().await.unwrap().take_result().unwrap(),
            array.join_next().await.unwrap().take_result().unwrap(),
            array.join_next().await.unwrap().take_result().unwrap(),
        ];
        outputs.sort();
        assert_eq!(outputs, [100, 101, 102]);

        for _ in 0..3 {
            assert_matches!(array.join_next().await, None);
        }
    }

    #[tokio::test]
    async fn shutdown() {
        async fn test<const N: usize>(
            array: &mut JoinArray<Result<(), ()>, N>,
            expect: Result<Result<(), ()>, ShutdownError>,
        ) {
            assert_eq!(
                array.shutdown_with_timeout(Duration::from_millis(10)).await,
                expect,
            );
        }

        fn spawn_ok() -> JoinGuard<Result<(), ()>> {
            JoinGuard::spawn(|cancel| async move { Ok(cancel.wait().await) })
        }

        fn spawn_err() -> JoinGuard<Result<(), ()>> {
            JoinGuard::spawn(|cancel| async move { Err(cancel.wait().await) })
        }

        fn spawn_pending() -> JoinGuard<Result<(), ()>> {
            JoinGuard::spawn(|_| future::pending())
        }

        let mut array = JoinArray::new([spawn_ok()]);
        test(&mut array, Ok(Ok(()))).await;

        let mut array = JoinArray::new([spawn_err()]);
        test(&mut array, Ok(Err(()))).await;

        let mut array = JoinArray::new([spawn_ok(), spawn_err()]);
        test(&mut array, Ok(Err(()))).await;

        let mut array = JoinArray::new([spawn_pending()]);
        test(&mut array, Err(ShutdownError::JoinTimeout)).await;

        let mut array = JoinArray::new([spawn_ok(), spawn_pending()]);
        test(&mut array, Err(ShutdownError::JoinTimeout)).await;

        let mut array = JoinArray::new([spawn_ok(), spawn_err(), spawn_pending()]);
        test(&mut array, Ok(Err(()))).await;
    }
}
