use std::collections::VecDeque;
use std::sync::{
    atomic::{AtomicUsize, Ordering},
    Arc, Mutex,
};

use tokio::sync::{Semaphore, SemaphorePermit, TryAcquireError};

use g1_base::sync::MutexExt;

pub mod error {
    #[derive(Copy, Clone, Debug, Eq, PartialEq)]
    pub struct SendError<T>(pub T);

    #[derive(Copy, Clone, Debug, Eq, PartialEq)]
    pub enum TrySendError<T> {
        Full(T),
        Closed(T),
    }
}

#[derive(Debug)]
pub struct Receiver<T>(Arc<Inner<T>>);

#[derive(Debug)]
pub struct Sender<T>(Arc<Inner<T>>);

#[derive(Debug)]
struct Inner<T> {
    queue: Queue<T>,
    // For automatically closing the queue when either all receivers or all senders are dropped.
    recv: AtomicUsize,
    send: AtomicUsize,
}

// This implementation is not very efficient, but it should be good enough for now.
#[derive(Debug)]
struct Queue<T> {
    queue: Mutex<VecDeque<T>>,
    free: Semaphore,
    used: Semaphore,
}

// Follow tokio's convention, which returns sender before receiver.
pub fn channel<T>(size: usize) -> (Sender<T>, Receiver<T>) {
    let inner = Arc::new(Inner::new(size));
    (Sender::new(inner.clone()), Receiver::new(inner))
}

impl<T> Clone for Receiver<T> {
    fn clone(&self) -> Self {
        Self::new(self.0.clone())
    }
}

impl<T> Clone for Sender<T> {
    fn clone(&self) -> Self {
        Self::new(self.0.clone())
    }
}

impl<T> Receiver<T> {
    fn new(inner: Arc<Inner<T>>) -> Self {
        inner.recv.fetch_add(1, Ordering::SeqCst);
        Self(inner)
    }
}

impl<T> Sender<T> {
    fn new(inner: Arc<Inner<T>>) -> Self {
        inner.send.fetch_add(1, Ordering::SeqCst);
        Self(inner)
    }
}

impl<T> Drop for Receiver<T> {
    fn drop(&mut self) {
        if self.0.recv.fetch_sub(1, Ordering::SeqCst) == 1 {
            self.0.queue.close()
        }
    }
}

impl<T> Drop for Sender<T> {
    fn drop(&mut self) {
        if self.0.send.fetch_sub(1, Ordering::SeqCst) == 1 {
            self.0.queue.close()
        }
    }
}

impl<T> Receiver<T> {
    pub fn is_closed(&self) -> bool {
        self.0.queue.is_closed()
    }

    pub fn close(&self) {
        self.0.queue.close()
    }

    pub async fn recv(&self) -> Option<T> {
        self.0.queue.recv().await
    }
}

impl<T> Sender<T> {
    pub fn is_closed(&self) -> bool {
        self.0.queue.is_closed()
    }

    pub fn close(&self) {
        self.0.queue.close()
    }

    pub async fn send(&self, message: T) -> Result<(), error::SendError<T>> {
        self.0.queue.send(message).await
    }

    pub fn try_send(&self, message: T) -> Result<(), error::TrySendError<T>> {
        self.0.queue.try_send(message)
    }
}

impl<T> Inner<T> {
    fn new(size: usize) -> Self {
        Self {
            queue: Queue::new(size),
            recv: AtomicUsize::new(0),
            send: AtomicUsize::new(0),
        }
    }
}

impl<T> Queue<T> {
    fn new(size: usize) -> Self {
        Self {
            queue: Mutex::new(VecDeque::new()),
            free: Semaphore::new(size),
            used: Semaphore::new(0),
        }
    }

    fn is_closed(&self) -> bool {
        self.free.is_closed()
    }

    fn close(&self) {
        self.free.close();
        self.used.close();
    }

    async fn recv(&self) -> Option<T> {
        match self.used.acquire().await {
            Ok(used_permit) => Some(self.pop(used_permit)),
            Err(_) => self.queue.must_lock().pop_front(),
        }
    }

    async fn send(&self, message: T) -> Result<(), error::SendError<T>> {
        match self.free.acquire().await {
            Ok(free_permit) => {
                self.push(message, free_permit);
                Ok(())
            }
            Err(_) => Err(error::SendError(message)),
        }
    }

    fn try_send(&self, message: T) -> Result<(), error::TrySendError<T>> {
        match self.free.try_acquire() {
            Ok(free_permit) => {
                self.push(message, free_permit);
                Ok(())
            }
            Err(TryAcquireError::NoPermits) => Err(error::TrySendError::Full(message)),
            Err(TryAcquireError::Closed) => Err(error::TrySendError::Closed(message)),
        }
    }

    fn pop(&self, used_permit: SemaphorePermit) -> T {
        let message = self.queue.must_lock().pop_front().unwrap();
        used_permit.forget();
        self.free.add_permits(1);
        message
    }

    fn push(&self, message: T, free_permit: SemaphorePermit) {
        self.queue.must_lock().push_back(message);
        free_permit.forget();
        self.used.add_permits(1);
    }
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use tokio::time;

    use super::*;

    impl<T> Inner<T> {
        fn assert(&self, recv: usize, send: usize) {
            assert_eq!(self.recv.load(Ordering::SeqCst), recv);
            assert_eq!(self.send.load(Ordering::SeqCst), send);
        }
    }

    impl<T> Queue<T> {
        fn assert(&self, closed: bool, size: usize) {
            assert_eq!(self.is_closed(), closed);
            assert_eq!(self.free.is_closed(), closed);
            assert_eq!(self.used.is_closed(), closed);
            assert_eq!(
                self.free.available_permits() + self.used.available_permits(),
                size
            );
            assert!(self.queue.must_lock().len() <= size);
        }
    }

    #[test]
    fn clone() {
        let (send_1, recv_1) = channel::<()>(10);
        let inner = send_1.0.clone();
        inner.assert(1, 1);

        let recv_2 = recv_1.clone();
        inner.assert(2, 1);

        let send_2 = send_1.clone();
        inner.assert(2, 2);

        drop(recv_1);
        inner.assert(1, 2);

        drop(send_2);
        inner.assert(1, 1);

        drop(send_1);
        inner.assert(1, 0);

        drop(recv_2);
        inner.assert(0, 0);
    }

    #[test]
    fn receiver_auto_close() {
        let (send, recv) = channel::<()>(10);
        send.0.assert(1, 1);
        send.0.queue.assert(false, 10);

        drop(recv);
        send.0.assert(0, 1);
        send.0.queue.assert(true, 10);
    }

    #[test]
    fn sender_auto_close() {
        let (send, recv) = channel::<()>(10);
        recv.0.assert(1, 1);
        recv.0.queue.assert(false, 10);

        drop(send);
        recv.0.assert(1, 0);
        recv.0.queue.assert(true, 10);
    }

    /*
    #[test]
    fn counters() {
        let (send_1, recv_1) = channel::<()>();
        let queue = send_1.0.clone();
        queue.assert_counters(1, 1);
        assert_eq!(queue.is_closed(), false);

        let send_2 = send_1.clone();
        queue.assert_counters(1, 2);
        assert_eq!(queue.is_closed(), false);

        let recv_2 = recv_1.clone();
        queue.assert_counters(2, 2);
        assert_eq!(queue.is_closed(), false);

        drop(send_2);
        queue.assert_counters(2, 1);
        assert_eq!(queue.is_closed(), false);

        drop(send_1);
        queue.assert_counters(2, 0);
        assert_eq!(queue.is_closed(), true);

        drop(recv_2);
        queue.assert_counters(1, 0);
        assert_eq!(queue.is_closed(), true);

        drop(recv_1);
        queue.assert_counters(0, 0);
        assert_eq!(queue.is_closed(), true);

        let (send, recv) = channel::<()>();
        let queue = send.0.clone();
        queue.assert_counters(1, 1);
        assert_eq!(queue.is_closed(), false);

        drop(recv);
        queue.assert_counters(0, 1);
        assert_eq!(queue.is_closed(), true);
    }
    */

    #[tokio::test]
    async fn close() {
        let queue = Queue::new(10);
        queue.assert(false, 10);

        assert_eq!(queue.send("foo").await, Ok(()));
        assert_eq!(queue.try_send("bar"), Ok(()));
        assert_eq!(queue.recv().await, Some("foo"));
        queue.assert(false, 10);

        queue.close();
        queue.assert(true, 10);

        assert_eq!(queue.send("spam").await, Err(error::SendError("spam")));
        assert_eq!(
            queue.try_send("egg"),
            Err(error::TrySendError::Closed("egg"))
        );
        assert_eq!(queue.recv().await, Some("bar"));
        assert_eq!(queue.recv().await, None);
        queue.assert(true, 10);
    }

    #[tokio::test]
    async fn recv_closed() {
        let queue = Arc::new(Queue::<()>::new(10));
        queue.assert(false, 10);

        let recv_task = {
            let queue = queue.clone();
            tokio::spawn(async move { queue.recv().await })
        };

        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(recv_task.is_finished(), false);
        queue.assert(false, 10);

        queue.close();
        assert!(matches!(recv_task.await, Ok(None)));
        queue.assert(true, 10);
    }

    #[tokio::test]
    async fn send_full() {
        let queue = Arc::new(Queue::new(1));
        queue.assert(false, 1);

        assert_eq!(queue.send("foo").await, Ok(()));
        queue.assert(false, 1);

        let send_task = {
            let queue = queue.clone();
            tokio::spawn(async move { queue.send("bar").await })
        };

        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(send_task.is_finished(), false);
        queue.assert(false, 1);

        assert_eq!(queue.recv().await, Some("foo"));
        assert!(matches!(send_task.await, Ok(Ok(()))));
        queue.assert(false, 1);

        assert_eq!(queue.recv().await, Some("bar"));
        queue.assert(false, 1);
    }

    #[test]
    fn try_send_full() {
        let queue = Queue::new(1);
        queue.assert(false, 1);

        assert_eq!(queue.try_send("foo"), Ok(()));
        queue.assert(false, 1);

        assert_eq!(queue.try_send("bar"), Err(error::TrySendError::Full("bar")));
        queue.assert(false, 1);
    }
}
