//! Outgoing block request queue.

use std::collections::{hash_map::Entry, HashMap, VecDeque};
use std::future::Future;
use std::pin::Pin;
use std::sync::{Arc, Mutex};
use std::task::{Context, Poll};
use std::time::Duration;

use bytes::Bytes;
use tokio::{
    sync::{mpsc, oneshot},
    time::{self, Instant},
};

use g1_base::sync::MutexExt;

use bittorrent_base::BlockDesc;

use crate::Full;

#[derive(Debug)]
pub(crate) struct QueueUpper {
    queue: Arc<Mutex<Queue>>,
    new_send: mpsc::UnboundedSender<BlockDesc>,
}

#[derive(Debug)]
pub(crate) struct QueueLower {
    queue: Arc<Mutex<Queue>>,
    pub(crate) new_recv: mpsc::UnboundedReceiver<BlockDesc>,
    pub(crate) cancel_recv: mpsc::UnboundedReceiver<BlockDesc>,
}

#[derive(Debug)]
struct Queue {
    requests: HashMap<BlockDesc, ResponseSend>,
    size: u64,
    limit: u64,

    // For now, we can use `VecDeque` because `timeout` is fixed.
    deadlines: VecDeque<(Instant, BlockDesc)>,
    timeout: Duration,

    choke: VecDeque<BlockDesc>,
    cancel_send: mpsc::UnboundedSender<BlockDesc>,
}

// The caller cancels the request by dropping `ResponseRecv`.
#[derive(Debug)]
pub struct ResponseRecv {
    recv: oneshot::Receiver<Bytes>,

    // We cannot use `Sender::closed` to get the cancellation because it requires `&mut self`.
    queue: Arc<Mutex<Queue>>,
    desc: BlockDesc,
}

pub(crate) type ResponseSend = oneshot::Sender<Bytes>;

pub(crate) fn new_queue(limit: u64, timeout: Duration) -> (QueueUpper, QueueLower) {
    let (new_send, new_recv) = mpsc::unbounded_channel();
    let (cancel_send, cancel_recv) = mpsc::unbounded_channel();
    let queue = Arc::new(Mutex::new(Queue::new(limit, timeout, cancel_send)));
    (
        QueueUpper {
            queue: queue.clone(),
            new_send,
        },
        QueueLower {
            queue,
            new_recv,
            cancel_recv,
        },
    )
}

impl QueueUpper {
    pub(crate) fn enqueue(&self, desc: BlockDesc) -> Result<Option<ResponseRecv>, Full> {
        Ok(self.queue.must_lock().enqueue(desc)?.map(|recv| {
            let _ = self.new_send.send(desc);
            ResponseRecv {
                recv,
                queue: self.queue.clone(),
                desc,
            }
        }))
    }
}

impl QueueLower {
    pub(crate) fn dequeue(&self, desc: BlockDesc) -> Option<ResponseSend> {
        self.queue.must_lock().dequeue(desc)
    }

    pub(crate) fn expired(&self) -> impl Future<Output = Option<BlockDesc>> {
        let queue = self.queue.clone();
        async move {
            loop {
                let deadline = match queue.must_lock().pop_expired(Instant::now()) {
                    Some(Err(deadline)) => deadline,
                    Some(Ok(desc)) => break Some(desc),
                    None => break None,
                };
                time::sleep_until(deadline).await;
            }
        }
    }

    pub(crate) fn push_choke(&self, desc: BlockDesc) {
        self.queue.must_lock().push_choke(desc);
    }

    pub(crate) fn take_choke(&self) -> VecDeque<BlockDesc> {
        self.queue.must_lock().take_choke()
    }
}

impl Queue {
    fn new(limit: u64, timeout: Duration, cancel_send: mpsc::UnboundedSender<BlockDesc>) -> Self {
        Self {
            requests: HashMap::new(),
            size: 0,
            limit,

            deadlines: VecDeque::new(),
            timeout,

            choke: VecDeque::new(),
            cancel_send,
        }
    }

    fn enqueue(&mut self, desc: BlockDesc) -> Result<Option<oneshot::Receiver<Bytes>>, Full> {
        match self.requests.entry(desc) {
            Entry::Occupied(_) => Ok(None),
            Entry::Vacant(entry) => {
                if self.size + desc.1 > self.limit {
                    return Err(Full);
                }

                let (response_send, response_recv) = oneshot::channel();
                entry.insert(response_send);
                self.size += desc.1;

                self.deadlines
                    .push_back((Instant::now() + self.timeout, desc));

                Ok(Some(response_recv))
            }
        }
    }

    fn dequeue(&mut self, desc: BlockDesc) -> Option<ResponseSend> {
        self.requests.remove(&desc).inspect(|_| {
            self.size -= desc.1;
        })
    }

    fn pop_expired(&mut self, now: Instant) -> Option<Result<BlockDesc, Instant>> {
        loop {
            let (deadline, desc) = self.deadlines.front().copied()?;
            if !self.requests.contains_key(&desc) {
                self.deadlines.pop_front().unwrap();
                continue;
            }
            return Some(if deadline <= now {
                self.deadlines.pop_front().unwrap();
                Ok(desc)
            } else {
                Err(deadline)
            });
        }
    }

    fn push_choke(&mut self, desc: BlockDesc) {
        self.choke.push_back(desc);
    }

    fn take_choke(&mut self) -> VecDeque<BlockDesc> {
        self.choke
            .drain(..)
            .filter(|desc| self.requests.contains_key(desc))
            .collect()
    }

    fn cancel(&mut self, desc: BlockDesc) {
        if self.dequeue(desc).is_some() {
            let _ = self.cancel_send.send(desc);
        }
    }
}

impl Future for ResponseRecv {
    type Output = Result<Bytes, oneshot::error::RecvError>;

    fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
        Pin::new(&mut self.get_mut().recv).poll(context)
    }
}

impl Drop for ResponseRecv {
    fn drop(&mut self) {
        self.queue.must_lock().cancel(self.desc);
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl QueueUpper {
        pub fn assert(
            &self,
            expect_descs: &[BlockDesc],
            expect_size: u64,
            expect_deadlines: &[BlockDesc],
            expect_choke: &[BlockDesc],
        ) {
            self.queue.must_lock().assert(
                expect_descs,
                expect_size,
                expect_deadlines,
                expect_choke,
            );
        }
    }

    impl QueueLower {
        pub fn assert(
            &self,
            expect_descs: &[BlockDesc],
            expect_size: u64,
            expect_deadlines: &[BlockDesc],
            expect_choke: &[BlockDesc],
        ) {
            self.queue.must_lock().assert(
                expect_descs,
                expect_size,
                expect_deadlines,
                expect_choke,
            );
        }
    }

    impl Queue {
        pub fn assert(
            &self,
            expect_descs: &[BlockDesc],
            expect_size: u64,
            expect_deadlines: &[BlockDesc],
            expect_choke: &[BlockDesc],
        ) {
            let mut descs: Vec<_> = self.requests.keys().copied().collect();
            descs.sort();
            assert_eq!(descs, expect_descs);

            assert_eq!(self.size, expect_size);

            assert!(self
                .deadlines
                .iter()
                .is_sorted_by_key(|(deadline, _)| deadline));
            assert_eq!(
                self.deadlines
                    .iter()
                    .map(|(_, desc)| *desc)
                    .collect::<Vec<_>>(),
                expect_deadlines,
            );

            assert_eq!(self.choke, expect_choke);
        }
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use bittorrent_base::{BlockOffset, PieceIndex};

    use super::*;

    const DESC1: BlockDesc = BlockDesc(BlockOffset(PieceIndex(0), 0), 1);
    const DESC2: BlockDesc = BlockDesc(BlockOffset(PieceIndex(0), 0), 2);
    const DESC3: BlockDesc = BlockDesc(BlockOffset(PieceIndex(0), 0), 3);
    const DESC7: BlockDesc = BlockDesc(BlockOffset(PieceIndex(0), 0), 7);

    #[tokio::test]
    async fn queue_upper() {
        let (upper, mut lower) = new_queue(10, Duration::ZERO);
        upper.assert(&[], 0, &[], &[]);

        let response_recv_3 = upper.enqueue(DESC3).unwrap().unwrap();
        upper.assert(&[DESC3], 3, &[DESC3], &[]);
        assert_eq!(lower.new_recv.recv().await, Some(DESC3));
        for _ in 0..3 {
            assert_matches!(upper.enqueue(DESC3), Ok(None));
            upper.assert(&[DESC3], 3, &[DESC3], &[]);
        }
        assert_matches!(lower.new_recv.try_recv(), Err(_));

        let response_recv_7 = upper.enqueue(DESC7).unwrap().unwrap();
        upper.assert(&[DESC3, DESC7], 10, &[DESC3, DESC7], &[]);
        assert_eq!(lower.new_recv.recv().await, Some(DESC7));
        for _ in 0..3 {
            assert_matches!(upper.enqueue(DESC7), Ok(None));
            upper.assert(&[DESC3, DESC7], 10, &[DESC3, DESC7], &[]);
        }
        assert_matches!(lower.new_recv.try_recv(), Err(_));

        assert_matches!(upper.enqueue(DESC1), Err(Full));
        upper.assert(&[DESC3, DESC7], 10, &[DESC3, DESC7], &[]);

        assert_matches!(lower.cancel_recv.try_recv(), Err(_));

        drop(response_recv_3);
        upper.assert(&[DESC7], 7, &[DESC3, DESC7], &[]);
        assert_matches!(lower.cancel_recv.recv().await, Some(desc) if desc == DESC3);
        assert_matches!(lower.cancel_recv.try_recv(), Err(_));

        drop(response_recv_7);
        upper.assert(&[], 0, &[DESC3, DESC7], &[]);
        assert_matches!(lower.cancel_recv.recv().await, Some(desc) if desc == DESC7);
        assert_matches!(lower.cancel_recv.try_recv(), Err(_));
    }

    #[tokio::test]
    async fn queue_lower() {
        let (_, lower) = new_queue(10, Duration::ZERO);
        {
            let mut guard = lower.queue.must_lock();
            assert_matches!(guard.enqueue(DESC1), Ok(Some(_)));
            assert_matches!(guard.enqueue(DESC2), Ok(Some(_)));
        }
        lower.assert(&[DESC1, DESC2], 3, &[DESC1, DESC2], &[]);

        assert_eq!(lower.expired().await, Some(DESC1));
        lower.assert(&[DESC1, DESC2], 3, &[DESC2], &[]);

        assert_eq!(lower.expired().await, Some(DESC2));
        lower.assert(&[DESC1, DESC2], 3, &[], &[]);

        assert_eq!(lower.expired().await, None);
        lower.assert(&[DESC1, DESC2], 3, &[], &[]);
    }

    #[tokio::test]
    async fn queue() {
        let (cancel_send, mut cancel_recv) = mpsc::unbounded_channel();
        let mut queue = Queue::new(10, Duration::ZERO, cancel_send);
        queue.assert(&[], 0, &[], &[]);

        assert_matches!(queue.enqueue(DESC3), Ok(Some(_)));
        queue.assert(&[DESC3], 3, &[DESC3], &[]);
        for _ in 0..3 {
            assert_matches!(queue.enqueue(DESC3), Ok(None));
            queue.assert(&[DESC3], 3, &[DESC3], &[]);
        }

        assert_matches!(queue.enqueue(DESC7), Ok(Some(_)));
        queue.assert(&[DESC3, DESC7], 10, &[DESC3, DESC7], &[]);
        assert_matches!(queue.enqueue(DESC1), Err(Full));
        queue.assert(&[DESC3, DESC7], 10, &[DESC3, DESC7], &[]);

        assert_matches!(queue.dequeue(DESC3), Some(_));
        queue.assert(&[DESC7], 7, &[DESC3, DESC7], &[]);
        for _ in 0..3 {
            assert_matches!(queue.dequeue(DESC3), None);
            queue.assert(&[DESC7], 7, &[DESC3, DESC7], &[]);
        }
        assert_matches!(cancel_recv.try_recv(), Err(_));

        queue.cancel(DESC7);
        queue.assert(&[], 0, &[DESC3, DESC7], &[]);
        assert_matches!(cancel_recv.recv().await, Some(desc) if desc == DESC7);
        for _ in 0..3 {
            queue.cancel(DESC7);
            queue.assert(&[], 0, &[DESC3, DESC7], &[]);
        }
        assert_matches!(cancel_recv.try_recv(), Err(_));
    }

    #[test]
    fn queue_pop_expired() {
        let (cancel_send, _) = mpsc::unbounded_channel();
        let mut queue = Queue::new(10, Duration::ZERO, cancel_send);
        queue.assert(&[], 0, &[], &[]);

        assert_eq!(queue.pop_expired(Instant::now()), None);

        let t0 = Instant::now();
        assert_matches!(queue.enqueue(DESC1), Ok(Some(_)));
        let t1 = Instant::now();
        assert_matches!(queue.enqueue(DESC2), Ok(Some(_)));
        let t2 = Instant::now();
        queue.assert(&[DESC1, DESC2], 3, &[DESC1, DESC2], &[]);

        assert_matches!(queue.pop_expired(t0), Some(Err(t)) if t0 < t && t < t1);
        queue.assert(&[DESC1, DESC2], 3, &[DESC1, DESC2], &[]);

        assert_matches!(queue.pop_expired(t1), Some(Ok(desc)) if desc == DESC1);
        queue.assert(&[DESC1, DESC2], 3, &[DESC2], &[]);

        assert_matches!(queue.pop_expired(t1), Some(Err(t)) if t1 < t && t < t2);
        queue.assert(&[DESC1, DESC2], 3, &[DESC2], &[]);

        assert_matches!(queue.pop_expired(t2), Some(Ok(desc)) if desc == DESC2);
        queue.assert(&[DESC1, DESC2], 3, &[], &[]);

        let (cancel_send, _) = mpsc::unbounded_channel();
        let mut queue = Queue::new(10, Duration::ZERO, cancel_send);
        assert_matches!(queue.enqueue(DESC1), Ok(Some(_)));
        assert_matches!(queue.enqueue(DESC2), Ok(Some(_)));
        assert_matches!(queue.dequeue(DESC1), Some(_));
        assert_matches!(queue.dequeue(DESC2), Some(_));
        queue.assert(&[], 0, &[DESC1, DESC2], &[]);

        assert_eq!(queue.pop_expired(Instant::now()), None);
        queue.assert(&[], 0, &[], &[]);
    }

    #[test]
    fn queue_choke() {
        let (cancel_send, _) = mpsc::unbounded_channel();
        let mut queue = Queue::new(10, Duration::ZERO, cancel_send);
        queue.assert(&[], 0, &[], &[]);

        queue.push_choke(DESC1);
        queue.assert(&[], 0, &[], &[DESC1]);
        queue.push_choke(DESC2);
        queue.assert(&[], 0, &[], &[DESC1, DESC2]);

        assert_eq!(queue.take_choke(), &[]);
        queue.assert(&[], 0, &[], &[]);

        assert_matches!(queue.enqueue(DESC1), Ok(Some(_)));
        queue.push_choke(DESC1);
        queue.push_choke(DESC2);
        queue.assert(&[DESC1], 1, &[DESC1], &[DESC1, DESC2]);

        assert_eq!(queue.take_choke(), &[DESC1]);
        queue.assert(&[DESC1], 1, &[DESC1], &[]);
    }
}
