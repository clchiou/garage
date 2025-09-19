//! Broadcast Queue
//!
//! Unlike the broadcast queue provided by `tokio`, ours applies back pressure to senders (though I
//! am not sure if this is a useful feature).

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};

use tokio::sync::Notify;

use g1_base::sync::MutexExt;

use self::error::{RecvError, SendError, TryRecvError, TrySendError};

pub mod error {
    use std::error::Error;
    use std::fmt::{self, Debug, Display};

    #[derive(Clone, Debug, Eq, PartialEq)]
    pub struct RecvError(pub(super) ());

    #[derive(Clone, Debug, Eq, PartialEq)]
    pub enum TryRecvError {
        Closed,
        Empty,
    }

    #[derive(Clone, Debug, Eq, PartialEq)]
    pub struct SendError<T>(pub T);

    #[derive(Clone, Debug, Eq, PartialEq)]
    pub enum TrySendError<T> {
        NoReceiver(T),
        Full(T),
    }

    impl Display for RecvError {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            write!(f, "channel closed")
        }
    }

    impl Display for TryRecvError {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            match self {
                Self::Closed => write!(f, "channel closed"),
                Self::Empty => write!(f, "channel empty"),
            }
        }
    }

    impl<T> Display for SendError<T> {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            write!(f, "no receiver")
        }
    }

    impl<T> Display for TrySendError<T> {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            match self {
                Self::NoReceiver(_) => write!(f, "no receiver"),
                Self::Full(_) => write!(f, "channel full"),
            }
        }
    }

    impl Error for RecvError {}
    impl Error for TryRecvError {}
    impl<T: Debug> Error for SendError<T> {}
    impl<T: Debug> Error for TrySendError<T> {}
}

//
// This implementation is not very efficient, but it should be good enough for now.
//

#[derive(Debug)]
pub struct Receiver<T> {
    shared: Arc<Shared<T>>,
    serial: usize,
}

#[derive(Debug)]
pub struct Sender<T>(Arc<Shared<T>>);

#[derive(Debug)]
struct Shared<T> {
    queue: Mutex<Queue<T>>,
    num_senders: AtomicUsize,
    notify_not_empty: Notify,
    notify_not_full: Notify,
}

#[derive(Debug)]
struct Queue<T> {
    buffer: Box<[Slot<T>]>,
    // `start` is a serial, not an index.
    start: usize,
    len: usize,
}

#[derive(Debug)]
#[cfg_attr(test, derive(PartialEq))]
struct Slot<T> {
    value: Option<T>,

    serial: usize,

    // Number of receivers who will read this slot.
    num_receivers: usize,

    // Number of receivers who will read this slot in the next cycle.  This number is incremented
    // when the buffer is full and a receiver is advanced to the next cycle.
    num_receivers_next_cycle: usize,
}

// Follow `tokio`'s convention, which returns sender before receiver.
pub fn channel<T: Clone>(capacity: usize) -> (Sender<T>, Receiver<T>) {
    let shared = Arc::new(Shared::new(capacity));
    (Sender::new(shared.clone()), Receiver::new(shared))
}

impl<T> Drop for Receiver<T> {
    fn drop(&mut self) {
        let mut queue = self.shared.queue.must_lock();
        let num_receivers = queue.num_receivers_mut(self.serial);
        *num_receivers -= 1;
        if *num_receivers == 0 {
            queue.cleanup();
        }
    }
}

impl<T> Receiver<T> {
    fn new(shared: Arc<Shared<T>>) -> Self {
        let mut queue = shared.queue.must_lock();
        // Receive values sent after it has subscribed.
        // NOTE: `Queue::cleanup` assumes that new receivers always start at the latest serial.
        let serial = queue.end();
        *queue.num_receivers_mut(serial) += 1;
        drop(queue);

        Self { shared, serial }
    }

    pub fn resubscribe(&self) -> Self {
        Self::new(self.shared.clone())
    }

    pub fn is_closed(&self) -> bool {
        self.shared.num_senders.load(Ordering::SeqCst) == 0
    }

    pub fn len(&self) -> usize {
        self.shared.queue.must_lock().len()
    }

    pub fn is_empty(&self) -> bool {
        self.shared.queue.must_lock().is_empty()
    }

    pub fn is_full(&self) -> bool {
        self.shared.queue.must_lock().is_full()
    }
}

impl<T> Receiver<T>
where
    T: Clone,
{
    pub async fn recv(&mut self) -> Result<T, RecvError> {
        tokio::pin! {
            let notify_not_empty = self.shared.notify_not_empty.notified();
        }
        loop {
            notify_not_empty.as_mut().enable();

            match self.recv_impl() {
                Some((value, serial)) => {
                    self.serial = serial;
                    return Ok(value);
                }
                None => {
                    if self.is_closed() {
                        return Err(RecvError(()));
                    }
                }
            }

            notify_not_empty.as_mut().await;

            notify_not_empty.set(self.shared.notify_not_empty.notified());
        }
    }

    pub fn try_recv(&mut self) -> Result<T, TryRecvError> {
        match self.recv_impl() {
            Some((value, serial)) => {
                self.serial = serial;
                Ok(value)
            }
            None => Err(if self.is_closed() {
                TryRecvError::Closed
            } else {
                TryRecvError::Empty
            }),
        }
    }

    // NOTE: Caller must update `self.serial`.
    fn recv_impl(&self) -> Option<(T, usize)> {
        let mut queue = self.shared.queue.must_lock();

        let value_and_serial = queue.read(self.serial)?;

        if !queue.is_full() {
            self.shared.notify_not_full.notify_one();
        }

        Some(value_and_serial)
    }
}

impl<T> Clone for Sender<T> {
    fn clone(&self) -> Self {
        Self::new(self.0.clone())
    }
}

impl<T> Drop for Sender<T> {
    fn drop(&mut self) {
        if self.0.num_senders.fetch_sub(1, Ordering::SeqCst) == 1 {
            // All `recv` calls should be unblocked when the channel is closed.
            self.0.notify_not_empty.notify_waiters();
        }
    }
}

impl<T> Sender<T> {
    fn new(shared: Arc<Shared<T>>) -> Self {
        shared.num_senders.fetch_add(1, Ordering::SeqCst);
        Self(shared)
    }

    pub fn subscribe(&self) -> Receiver<T> {
        Receiver::new(self.0.clone())
    }

    pub fn len(&self) -> usize {
        self.0.queue.must_lock().len()
    }

    pub fn is_empty(&self) -> bool {
        self.0.queue.must_lock().is_empty()
    }

    pub fn is_full(&self) -> bool {
        self.0.queue.must_lock().is_full()
    }

    pub async fn send(&self, mut value: T) -> Result<(), SendError<T>> {
        tokio::pin! {
            let notify_not_full = self.0.notify_not_full.notified();
        }
        loop {
            notify_not_full.as_mut().enable();

            value = match self.try_send(value) {
                Ok(()) => return Ok(()),
                Err(TrySendError::NoReceiver(value)) => return Err(SendError(value)),
                Err(TrySendError::Full(value)) => value,
            };

            notify_not_full.as_mut().await;

            notify_not_full.set(self.0.notify_not_full.notified());
        }
    }

    pub fn try_send(&self, value: T) -> Result<(), TrySendError<T>> {
        self.0
            .queue
            .must_lock()
            .push(value)
            .inspect(|_| self.0.notify_not_empty.notify_waiters())
    }
}

impl<T> Shared<T> {
    fn new(capacity: usize) -> Self {
        Self {
            queue: Mutex::new(Queue::new(capacity)),
            num_senders: AtomicUsize::new(0),
            notify_not_empty: Notify::new(),
            notify_not_full: Notify::new(),
        }
    }
}

impl<T> Queue<T> {
    fn new(capacity: usize) -> Self {
        // NOTE: `capacity` must be a power of two because serials might wrap around.
        assert!(
            0 < capacity && capacity <= usize::MAX / 2,
            "capacity = {capacity}",
        );
        let capacity = capacity.next_power_of_two();

        let mut buffer = Vec::with_capacity(capacity);
        for serial in 0..capacity {
            buffer.push(Slot {
                value: None,
                serial,
                num_receivers: 0,
                num_receivers_next_cycle: 0,
            });
        }

        Self {
            buffer: buffer.into_boxed_slice(),
            start: 0,
            len: 0,
        }
    }

    // This returns a serial, not an index.
    fn end(&self) -> usize {
        self.start.wrapping_add(self.len)
    }

    fn num_receivers_mut(&mut self, serial: usize) -> &mut usize {
        let i = serial % self.buffer.len();
        if self.buffer[i].serial == serial {
            &mut self.buffer[i].num_receivers
        } else {
            assert_eq!(
                self.buffer[i].serial.wrapping_add(self.buffer.len()),
                serial,
            );
            &mut self.buffer[i].num_receivers_next_cycle
        }
    }

    fn len(&self) -> usize {
        self.len
    }

    fn is_empty(&self) -> bool {
        self.len == 0
    }

    fn is_full(&self) -> bool {
        self.len >= self.buffer.len()
    }

    fn push(&mut self, value: T) -> Result<(), TrySendError<T>> {
        if self.len >= self.buffer.len() {
            return Err(TrySendError::Full(value));
        }

        let end = self.end();
        let i = end % self.buffer.len();

        // This slot must be vacant.
        assert!(self.buffer[i].value.is_none());
        assert_eq!(self.buffer[i].serial, end);

        // Write to this slot only if there are receivers who will read it.
        if self.len > 0 || self.buffer[i].num_receivers > 0 {
            self.buffer[i].value = Some(value);
            self.len += 1;
            Ok(())
        } else {
            Err(TrySendError::NoReceiver(value))
        }
    }

    /// Reads the value at `serial` and advances it by adjusting `num_receivers`.
    ///
    /// The caller must ensure that a receiver does not read the same serial twice.
    fn read(&mut self, serial: usize) -> Option<(T, usize)>
    where
        T: Clone,
    {
        let i = serial % self.buffer.len();
        if self.buffer[i].serial != serial {
            // `serial` is in the next cycle.
            assert_eq!(
                self.buffer[i].serial.wrapping_add(self.buffer.len()),
                serial,
            );
            return None;
        }

        // Return `None` if the caller reads past the end.
        let value = self.buffer[i].value.clone()?;
        let serial_next = serial.wrapping_add(1);

        self.buffer[i].num_receivers -= 1;
        *self.num_receivers_mut(serial_next) += 1;

        // Free up slots for the next cycle.
        self.cleanup();

        Some((value, serial_next))
    }

    // NOTE: This assumes that new subscribers always start at the latest serial, meaning earlier
    // serials will not be read and can be dropped.
    fn cleanup(&mut self) {
        let mut i = self.start % self.buffer.len();
        while self.len > 0 && self.buffer[i].num_receivers == 0 {
            // This slot must be occupied.
            assert!(self.buffer[i].value.is_some());
            assert_eq!(self.buffer[i].serial, self.start);

            // Clear the slot and prepare it for the next cycle.
            self.buffer[i].value = None;
            self.buffer[i].serial = self.buffer[i].serial.wrapping_add(self.buffer.len());
            self.buffer[i].num_receivers = self.buffer[i].num_receivers_next_cycle;
            self.buffer[i].num_receivers_next_cycle = 0;

            self.start = self.start.wrapping_add(1);
            self.len -= 1;

            i = self.start % self.buffer.len();
        }
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::fmt::Debug;
    use std::time::Duration;

    use tokio::time;

    use super::*;

    impl<T> Receiver<T>
    where
        T: Debug + PartialEq,
    {
        fn assert<const N: usize>(
            &self,
            buffer: [(Option<T>, usize, usize, usize); N],
            start: usize,
            len: usize,
            num_senders: usize,
            serial: usize,
        ) {
            self.shared.assert(buffer, start, len, num_senders);
            assert_eq!(self.serial, serial);
        }
    }

    impl<T> Sender<T>
    where
        T: Debug + PartialEq,
    {
        fn assert<const N: usize>(
            &self,
            buffer: [(Option<T>, usize, usize, usize); N],
            start: usize,
            len: usize,
            num_senders: usize,
        ) {
            self.0.assert(buffer, start, len, num_senders);
        }
    }

    impl<T> Shared<T>
    where
        T: Debug + PartialEq,
    {
        fn assert<const N: usize>(
            &self,
            buffer: [(Option<T>, usize, usize, usize); N],
            start: usize,
            len: usize,
            num_senders: usize,
        ) {
            self.queue.must_lock().assert(buffer, start, len);
            assert_eq!(self.num_senders.load(Ordering::SeqCst), num_senders);
        }
    }

    impl<T> Queue<T>
    where
        T: Debug + PartialEq,
    {
        fn assert<const N: usize>(
            &self,
            buffer: [(Option<T>, usize, usize, usize); N],
            start: usize,
            len: usize,
        ) {
            let buffer = buffer
                .into_iter()
                .map(
                    |(value, serial, num_receivers, num_receivers_next_cycle)| Slot {
                        value,
                        serial,
                        num_receivers,
                        num_receivers_next_cycle,
                    },
                )
                .collect::<Vec<_>>();
            assert_eq!(&*self.buffer, buffer);
            assert_eq!(self.start, start);
            assert_eq!(self.len, len);
        }
    }

    //
    // TODO: Can we write these tests without using `time::sleep`?
    //

    #[test]
    fn num_receivers() {
        {
            let (s, r) = channel::<()>(1);
            s.assert([(None, 0, 1, 0)], 0, 0, 1);

            drop(r);
            s.assert([(None, 0, 0, 0)], 0, 0, 1);
        }

        {
            let (s, r0) = channel::<()>(1);
            let r1 = r0.resubscribe();
            let r2 = s.subscribe();
            s.assert([(None, 0, 3, 0)], 0, 0, 1);

            drop(r0);
            s.assert([(None, 0, 2, 0)], 0, 0, 1);
            drop(r1);
            s.assert([(None, 0, 1, 0)], 0, 0, 1);
            drop(r2);
            s.assert([(None, 0, 0, 0)], 0, 0, 1);
        }

        {
            let (s, mut r0) = channel(1);
            let r1 = r0.resubscribe();
            assert_eq!(s.try_send('a'), Ok(()));
            assert_eq!(r0.try_recv(), Ok('a'));
            s.assert([(Some('a'), 0, 1, 1)], 0, 1, 1);

            drop(r0);
            s.assert([(Some('a'), 0, 1, 0)], 0, 1, 1);
            drop(r1);
            s.assert([(None, 1, 0, 0)], 1, 0, 1);
        }

        {
            let (s, mut r0) = channel(1);
            let r1 = r0.resubscribe();
            assert_eq!(s.try_send('a'), Ok(()));
            assert_eq!(r0.try_recv(), Ok('a'));
            s.assert([(Some('a'), 0, 1, 1)], 0, 1, 1);

            drop(r1);
            s.assert([(None, 1, 1, 0)], 1, 0, 1);
            drop(r0);
            s.assert([(None, 1, 0, 0)], 1, 0, 1);
        }

        {
            let (s, r) = channel(1);
            assert_eq!(s.try_send('a'), Ok(()));
            s.assert([(Some('a'), 0, 1, 0)], 0, 1, 1);

            drop(r);
            s.assert([(None, 1, 0, 0)], 1, 0, 1);
        }

        {
            let (s, r0) = channel(2);

            assert_eq!(s.try_send('a'), Ok(()));
            let r1 = r0.resubscribe();

            assert_eq!(s.try_send('b'), Ok(()));
            let r2 = s.subscribe();

            assert_eq!(r0.serial, 0);
            assert_eq!(r1.serial, 1);
            assert_eq!(r2.serial, 2);
        }
    }

    #[tokio::test]
    async fn recv() {
        async fn collect(mut r: Receiver<char>) -> Vec<char> {
            let mut cs = Vec::new();
            while let Ok(c) = r.recv().await {
                cs.push(c);
            }
            cs
        }

        let (s, r0) = channel(1);
        let r1 = r0.resubscribe();
        let r2 = s.subscribe();

        let task0 = tokio::spawn(async move { collect(r0).await });
        let task1 = tokio::spawn(async move { collect(r1).await });
        let task2 = tokio::spawn(async move { collect(r2).await });

        assert_eq!(s.send('a').await, Ok(()));
        assert_eq!(s.send('b').await, Ok(()));
        assert_eq!(s.send('c').await, Ok(()));
        drop(s);

        assert_matches!(task0.await, Ok(cs) if cs == ['a', 'b', 'c']);
        assert_matches!(task1.await, Ok(cs) if cs == ['a', 'b', 'c']);
        assert_matches!(task2.await, Ok(cs) if cs == ['a', 'b', 'c']);
    }

    #[test]
    fn try_recv() {
        let (s, mut r) = channel(1);
        assert_eq!(r.try_recv(), Err(TryRecvError::Empty));

        assert_eq!(s.try_send('a'), Ok(()));
        assert_eq!(r.try_recv(), Ok('a'));

        assert_eq!(s.try_send('b'), Ok(()));
        assert_eq!(r.try_recv(), Ok('b'));

        drop(s);
        assert_eq!(r.try_recv(), Err(TryRecvError::Closed));
    }

    #[test]
    fn num_senders() {
        {
            let (s, r) = channel::<()>(1);
            r.assert([(None, 0, 1, 0)], 0, 0, 1, 0);

            drop(s);
            r.assert([(None, 0, 1, 0)], 0, 0, 0, 0);
        }

        {
            let (s0, r) = channel::<()>(1);
            let s1 = s0.clone();
            r.assert([(None, 0, 1, 0)], 0, 0, 2, 0);

            drop(s0);
            r.assert([(None, 0, 1, 0)], 0, 0, 1, 0);
            drop(s1);
            r.assert([(None, 0, 1, 0)], 0, 0, 0, 0);
        }
    }

    #[tokio::test]
    async fn num_senders_unblock_recv() {
        let (s, mut r0) = channel::<()>(1);
        let mut r1 = r0.resubscribe();
        let mut r2 = s.subscribe();

        let task = tokio::spawn(async move { (r0.recv().await, r1.recv().await, r2.recv().await) });
        time::sleep(Duration::from_millis(10)).await;
        assert_eq!(task.is_finished(), false);

        drop(s);
        assert_matches!(
            task.await,
            Ok((Err(RecvError(())), Err(RecvError(())), Err(RecvError(())))),
        );
    }

    #[tokio::test]
    async fn send() {
        {
            let (s0, mut r) = channel(1);
            let s1 = s0.clone();

            let task0 = tokio::spawn(async move { s0.send(()).await });
            let task1 = tokio::spawn(async move { s1.send(()).await });

            assert_eq!(r.recv().await, Ok(()));
            assert_eq!(r.recv().await, Ok(()));

            assert_matches!(task0.await, Ok(Ok(())));
            assert_matches!(task1.await, Ok(Ok(())));

            assert_eq!(r.try_recv(), Err(TryRecvError::Closed));
        }

        {
            let (s, _) = channel(1);
            assert_eq!(s.send('a').await, Err(SendError('a')));
        }
    }

    #[test]
    fn try_send() {
        {
            let (s, mut r) = channel(2);

            assert_eq!(s.try_send('a'), Ok(()));
            assert_eq!(s.try_send('b'), Ok(()));
            assert!(s.is_full());
            assert_eq!(s.try_send('c'), Err(TrySendError::Full('c')));

            assert_eq!(r.try_recv(), Ok('a'));
            assert!(!s.is_full());
            assert_eq!(s.try_send('d'), Ok(()));

            assert_eq!(r.try_recv(), Ok('b'));
            assert_eq!(r.try_recv(), Ok('d'));
            assert!(s.is_empty());
        }

        {
            let (s, _) = channel(1);
            assert_eq!(s.try_send('a'), Err(TrySendError::NoReceiver('a')));
        }
    }

    #[test]
    fn queue_power_of_two() {
        assert_eq!(Queue::<()>::new(3).buffer.len(), 4);

        assert_eq!(Queue::<()>::new(6).buffer.len(), 8);
        assert_eq!(Queue::<()>::new(7).buffer.len(), 8);

        assert_eq!(Queue::<()>::new(11).buffer.len(), 16);
        assert_eq!(Queue::<()>::new(16).buffer.len(), 16);
    }

    #[test]
    fn queue_push() {
        {
            let mut queue = Queue::new(1);
            queue.assert([(None, 0, 0, 0)], 0, 0);

            assert_eq!(queue.push('a'), Err(TrySendError::NoReceiver('a')));
            queue.assert([(None, 0, 0, 0)], 0, 0);

            *queue.num_receivers_mut(0) = 1;
            queue.assert([(None, 0, 1, 0)], 0, 0);

            assert_eq!(queue.push('b'), Ok(()));
            queue.assert([(Some('b'), 0, 1, 0)], 0, 1);

            assert_eq!(queue.push('c'), Err(TrySendError::Full('c')));
            queue.assert([(Some('b'), 0, 1, 0)], 0, 1);
        }

        {
            let mut queue = Queue::new(1);
            queue.buffer[0].serial = usize::MAX;
            *queue.num_receivers_mut(usize::MAX) = 1;
            queue.start = usize::MAX;
            queue.assert([(None, usize::MAX, 1, 0)], usize::MAX, 0);

            assert_eq!(queue.push('a'), Ok(()));
            queue.assert([(Some('a'), usize::MAX, 1, 0)], usize::MAX, 1);

            assert_eq!(queue.push('b'), Err(TrySendError::Full('b')));
            queue.assert([(Some('a'), usize::MAX, 1, 0)], usize::MAX, 1);
        }

        {
            let mut queue = Queue::new(2);
            queue.assert([(None, 0, 0, 0), (None, 1, 0, 0)], 0, 0);

            assert_eq!(queue.push('a'), Err(TrySendError::NoReceiver('a')));
            queue.assert([(None, 0, 0, 0), (None, 1, 0, 0)], 0, 0);

            *queue.num_receivers_mut(0) = 1;
            queue.assert([(None, 0, 1, 0), (None, 1, 0, 0)], 0, 0);

            assert_eq!(queue.push('b'), Ok(()));
            queue.assert([(Some('b'), 0, 1, 0), (None, 1, 0, 0)], 0, 1);

            assert_eq!(queue.push('c'), Ok(()));
            queue.assert([(Some('b'), 0, 1, 0), (Some('c'), 1, 0, 0)], 0, 2);

            assert_eq!(queue.push('d'), Err(TrySendError::Full('d')));
            queue.assert([(Some('b'), 0, 1, 0), (Some('c'), 1, 0, 0)], 0, 2);
        }
    }

    #[test]
    fn queue_read() {
        {
            let mut queue = Queue::new(1);
            queue.assert([(None, 0, 0, 0)], 0, 0);

            assert_eq!(queue.read(0), None);
            queue.assert([(None, 0, 0, 0)], 0, 0);
            assert_eq!(queue.read(1), None);
            queue.assert([(None, 0, 0, 0)], 0, 0);

            *queue.num_receivers_mut(0) = 1;
            assert_eq!(queue.push('a'), Ok(()));
            queue.assert([(Some('a'), 0, 1, 0)], 0, 1);

            // Next cycle.
            assert_eq!(queue.read(1), None);
            queue.assert([(Some('a'), 0, 1, 0)], 0, 1);

            assert_eq!(queue.read(0), Some(('a', 1)));
            queue.assert([(None, 1, 1, 0)], 1, 0);

            assert_eq!(queue.read(1), None);
            queue.assert([(None, 1, 1, 0)], 1, 0);
            assert_eq!(queue.read(2), None);
            queue.assert([(None, 1, 1, 0)], 1, 0);

            assert_eq!(queue.push('b'), Ok(()));
            queue.assert([(Some('b'), 1, 1, 0)], 1, 1);

            // Next cycle.
            assert_eq!(queue.read(2), None);
            queue.assert([(Some('b'), 1, 1, 0)], 1, 1);

            assert_eq!(queue.read(1), Some(('b', 2)));
            queue.assert([(None, 2, 1, 0)], 2, 0);
        }

        {
            let mut queue = Queue::new(1);
            *queue.num_receivers_mut(0) = 2;
            assert_eq!(queue.push('a'), Ok(()));
            queue.assert([(Some('a'), 0, 2, 0)], 0, 1);

            assert_eq!(queue.read(0), Some(('a', 1)));
            queue.assert([(Some('a'), 0, 1, 1)], 0, 1);
            assert_eq!(queue.read(0), Some(('a', 1)));
            queue.assert([(None, 1, 2, 0)], 1, 0);
        }

        {
            let mut queue = Queue::new(1);
            queue.buffer[0].serial = usize::MAX;
            *queue.num_receivers_mut(usize::MAX) = 1;
            queue.start = usize::MAX;
            assert_eq!(queue.push('a'), Ok(()));
            queue.assert([(Some('a'), usize::MAX, 1, 0)], usize::MAX, 1);

            // Next cycle.
            assert_eq!(queue.read(0), None);
            queue.assert([(Some('a'), usize::MAX, 1, 0)], usize::MAX, 1);

            assert_eq!(queue.read(usize::MAX), Some(('a', 0)));
            queue.assert([(None, 0, 1, 0)], 0, 0);
        }

        {
            let mut queue = Queue::new(2);
            queue.assert([(None, 0, 0, 0), (None, 1, 0, 0)], 0, 0);

            assert_eq!(queue.push('a'), Err(TrySendError::NoReceiver('a')));
            queue.assert([(None, 0, 0, 0), (None, 1, 0, 0)], 0, 0);

            *queue.num_receivers_mut(0) = 1;
            assert_eq!(queue.push('b'), Ok(()));
            queue.assert([(Some('b'), 0, 1, 0), (None, 1, 0, 0)], 0, 1);

            assert_eq!(queue.read(0), Some(('b', 1)));
            queue.assert([(None, 2, 0, 0), (None, 1, 1, 0)], 1, 0);

            assert_eq!(queue.push('c'), Ok(()));
            queue.assert([(None, 2, 0, 0), (Some('c'), 1, 1, 0)], 1, 1);
            assert_eq!(queue.push('d'), Ok(()));
            queue.assert([(Some('d'), 2, 0, 0), (Some('c'), 1, 1, 0)], 1, 2);
            assert_eq!(queue.push('e'), Err(TrySendError::Full('e')));
            queue.assert([(Some('d'), 2, 0, 0), (Some('c'), 1, 1, 0)], 1, 2);

            assert_eq!(queue.read(1), Some(('c', 2)));
            queue.assert([(Some('d'), 2, 1, 0), (None, 3, 0, 0)], 2, 1);

            assert_eq!(queue.read(2), Some(('d', 3)));
            queue.assert([(None, 4, 0, 0), (None, 3, 1, 0)], 3, 0);
        }

        {
            let mut queue = Queue::new(2);
            *queue.num_receivers_mut(0) = 2;
            assert_eq!(queue.push('a'), Ok(()));
            assert_eq!(queue.push('b'), Ok(()));
            queue.assert([(Some('a'), 0, 2, 0), (Some('b'), 1, 0, 0)], 0, 2);

            assert_eq!(queue.read(0), Some(('a', 1)));
            queue.assert([(Some('a'), 0, 1, 0), (Some('b'), 1, 1, 0)], 0, 2);

            assert_eq!(queue.read(1), Some(('b', 2)));
            queue.assert([(Some('a'), 0, 1, 1), (Some('b'), 1, 0, 0)], 0, 2);

            assert_eq!(queue.read(0), Some(('a', 1)));
            queue.assert([(None, 2, 1, 0), (Some('b'), 1, 1, 0)], 1, 1);

            assert_eq!(queue.read(1), Some(('b', 2)));
            queue.assert([(None, 2, 2, 0), (None, 3, 0, 0)], 2, 0);
        }

        {
            let mut queue = Queue::new(4);
            *queue.num_receivers_mut(0) = 1;
            assert_eq!(queue.push('a'), Ok(()));
            assert_eq!(queue.push('b'), Ok(()));
            assert_eq!(queue.push('c'), Ok(()));
            assert_eq!(queue.push('d'), Ok(()));
            queue.assert(
                [
                    (Some('a'), 0, 1, 0),
                    (Some('b'), 1, 0, 0),
                    (Some('c'), 2, 0, 0),
                    (Some('d'), 3, 0, 0),
                ],
                0,
                4,
            );

            assert_eq!(queue.read(0), Some(('a', 1)));
            queue.assert(
                [
                    (None, 4, 0, 0),
                    (Some('b'), 1, 1, 0),
                    (Some('c'), 2, 0, 0),
                    (Some('d'), 3, 0, 0),
                ],
                1,
                3,
            );

            assert_eq!(queue.read(1), Some(('b', 2)));
            queue.assert(
                [
                    (None, 4, 0, 0),
                    (None, 5, 0, 0),
                    (Some('c'), 2, 1, 0),
                    (Some('d'), 3, 0, 0),
                ],
                2,
                2,
            );

            assert_eq!(queue.read(2), Some(('c', 3)));
            queue.assert(
                [
                    (None, 4, 0, 0),
                    (None, 5, 0, 0),
                    (None, 6, 0, 0),
                    (Some('d'), 3, 1, 0),
                ],
                3,
                1,
            );

            assert_eq!(queue.read(3), Some(('d', 4)));
            queue.assert(
                [
                    (None, 4, 1, 0),
                    (None, 5, 0, 0),
                    (None, 6, 0, 0),
                    (None, 7, 0, 0),
                ],
                4,
                0,
            );
        }
    }

    #[test]
    fn queue_cleanup() {
        {
            let mut queue = Queue::new(4);
            *queue.num_receivers_mut(0) = 1;
            *queue.num_receivers_mut(2) = 1;
            assert_eq!(queue.push('a'), Ok(()));
            assert_eq!(queue.push('b'), Ok(()));
            assert_eq!(queue.push('c'), Ok(()));
            assert_eq!(queue.push('d'), Ok(()));
            *queue.num_receivers_mut(0) = 0;
            *queue.num_receivers_mut(4) = 99;
            queue.assert(
                [
                    (Some('a'), 0, 0, 99),
                    (Some('b'), 1, 0, 0),
                    (Some('c'), 2, 1, 0),
                    (Some('d'), 3, 0, 0),
                ],
                0,
                4,
            );

            queue.cleanup();
            queue.assert(
                [
                    (None, 4, 99, 0),
                    (None, 5, 0, 0),
                    (Some('c'), 2, 1, 0),
                    (Some('d'), 3, 0, 0),
                ],
                2,
                2,
            );
        }

        {
            let mut queue = Queue::new(4);
            *queue.num_receivers_mut(0) = 1;
            assert_eq!(queue.push('a'), Ok(()));
            assert_eq!(queue.push('b'), Ok(()));
            assert_eq!(queue.push('c'), Ok(()));
            assert_eq!(queue.push('d'), Ok(()));
            *queue.num_receivers_mut(0) = 0;
            queue.assert(
                [
                    (Some('a'), 0, 0, 0),
                    (Some('b'), 1, 0, 0),
                    (Some('c'), 2, 0, 0),
                    (Some('d'), 3, 0, 0),
                ],
                0,
                4,
            );

            queue.cleanup();
            queue.assert(
                [
                    (None, 4, 0, 0),
                    (None, 5, 0, 0),
                    (None, 6, 0, 0),
                    (None, 7, 0, 0),
                ],
                4,
                0,
            );
        }
    }
}
