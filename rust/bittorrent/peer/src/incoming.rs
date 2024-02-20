//! Incoming block request queue.

use std::collections::HashMap;
use std::sync::Mutex;

use bytes::Bytes;
use tokio::sync::oneshot::{self, error::RecvError, Sender};

use g1_base::sync::MutexExt;
use g1_tokio::task::{Cancel, JoinGuard, JoinQueue};

use bittorrent_base::BlockDesc;

use crate::Full;

#[derive(Debug)]
pub(crate) struct Queue {
    inner: Mutex<Inner>,
    tasks: JoinQueue<Option<(BlockDesc, Result<Bytes, RecvError>)>>,
}

#[derive(Debug)]
struct Inner {
    requests: HashMap<BlockDesc, Cancel>,
    size: u64,
    limit: u64,
}

// The caller rejects the request by dropping `ResponseSend`.
pub type ResponseSend = Sender<Bytes>;

pub(crate) type Response = Result<Bytes, Reject>;

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct Reject;

impl Queue {
    pub(crate) fn new(limit: u64, cancel: Cancel) -> Self {
        Self {
            inner: Mutex::new(Inner::new(limit)),
            tasks: JoinQueue::with_cancel(cancel),
        }
    }

    pub(crate) fn enqueue(&self, desc: BlockDesc) -> Result<Option<ResponseSend>, Full> {
        // Unfortunately we cannot use `HashMap::entry` here.
        let mut inner = self.inner.must_lock();
        if !inner.can_insert(desc)? {
            return Ok(None);
        }
        let (response_send, response_recv) = oneshot::channel();
        let guard = JoinGuard::spawn(move |cancel| async move {
            tokio::select! {
                response = response_recv => Some((desc, response)),
                _ = cancel.wait() => None,
            }
        });
        let cancel = guard.cancel_handle();
        if self.tasks.push(guard).is_err() {
            return Ok(None);
        }
        inner.insert(desc, cancel);
        Ok(Some(response_send))
    }

    pub(crate) fn cancel(&self, desc: BlockDesc) {
        if let Some(cancel) = self.inner.must_lock().remove(desc) {
            cancel.set();
        }
    }

    pub(crate) async fn dequeue(&self) -> Option<(BlockDesc, Response)> {
        loop {
            if let Ok(Some((desc, result))) = self.tasks.join_next().await?.take_result() {
                let _ = self.inner.must_lock().remove(desc);
                return Some((desc, result.map_err(|_| Reject)));
            }
        }
    }
}

impl Inner {
    fn new(limit: u64) -> Self {
        Self {
            requests: HashMap::new(),
            size: 0,
            limit,
        }
    }

    fn can_insert(&self, desc: BlockDesc) -> Result<bool, Full> {
        if self.requests.contains_key(&desc) {
            Ok(false)
        } else if self.size + desc.1 > self.limit {
            Err(Full)
        } else {
            Ok(true)
        }
    }

    fn insert(&mut self, desc: BlockDesc, cancel: Cancel) {
        assert!(self.requests.insert(desc, cancel).is_none());
        self.size += desc.1;
        assert!(self.size <= self.limit);
    }

    fn remove(&mut self, desc: BlockDesc) -> Option<Cancel> {
        self.requests.remove(&desc).inspect(|_| self.size -= desc.1)
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl Queue {
        pub fn assert(&self, expect_descs: &[BlockDesc], expect_size: u64) {
            self.inner.must_lock().assert(expect_descs, expect_size);
        }
    }

    impl Inner {
        pub fn assert(&self, expect_descs: &[BlockDesc], expect_size: u64) {
            let mut descs: Vec<_> = self.requests.keys().copied().collect();
            descs.sort();
            assert_eq!(descs, expect_descs);
            assert_eq!(self.size, expect_size);
        }
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::time::Duration;

    use tokio::time;

    use bittorrent_base::{BlockOffset, PieceIndex};

    use super::*;

    const DESC2: BlockDesc = BlockDesc(BlockOffset(PieceIndex(0), 0), 2);
    const DESC3: BlockDesc = BlockDesc(BlockOffset(PieceIndex(0), 0), 3);
    const DESC4: BlockDesc = BlockDesc(BlockOffset(PieceIndex(0), 0), 4);
    const DESC6: BlockDesc = BlockDesc(BlockOffset(PieceIndex(0), 0), 6);
    const DESC7: BlockDesc = BlockDesc(BlockOffset(PieceIndex(0), 0), 7);
    const DESC8: BlockDesc = BlockDesc(BlockOffset(PieceIndex(0), 0), 8);
    const DESC10: BlockDesc = BlockDesc(BlockOffset(PieceIndex(0), 0), 10);
    const DESC11: BlockDesc = BlockDesc(BlockOffset(PieceIndex(0), 0), 11);

    #[tokio::test]
    async fn queue() {
        let queue = Queue::new(10, Cancel::new());
        queue.assert(&[], 0);
        assert_eq!(queue.tasks.len(), 0);

        assert_matches!(queue.enqueue(DESC3), Ok(Some(_)));
        queue.assert(&[DESC3], 3);
        assert_eq!(queue.tasks.len(), 1);
        for _ in 0..3 {
            assert_matches!(queue.enqueue(DESC3), Ok(None));
            queue.assert(&[DESC3], 3);
            assert_eq!(queue.tasks.len(), 1);
        }

        assert_matches!(queue.enqueue(DESC8), Err(Full));
        queue.assert(&[DESC3], 3);
        assert_eq!(queue.tasks.len(), 1);

        assert_eq!(queue.dequeue().await, Some((DESC3, Err(Reject))));
        queue.assert(&[], 0);
        assert_eq!(queue.tasks.len(), 0);
    }

    #[tokio::test]
    async fn queue_cancel() {
        let queue = Queue::new(10, Cancel::new());
        queue.assert(&[], 0);
        assert_eq!(queue.tasks.len(), 0);

        let response_send = queue.enqueue(DESC3).unwrap().unwrap();
        queue.assert(&[DESC3], 3);
        assert_eq!(queue.tasks.len(), 1);

        queue.cancel(DESC3);
        queue.assert(&[], 0);

        // TODO: Can we write this test without using `time::sleep`?
        time::sleep(Duration::from_millis(10)).await;

        assert_matches!(response_send.send(Bytes::from_static(b"spam")), Err(_));
        assert_eq!(
            queue.tasks.join_next().await.unwrap().take_result(),
            Ok(None),
        );
        assert_eq!(queue.tasks.len(), 0);
    }

    #[tokio::test]
    async fn queue_dequeue() {
        let queue = Queue::new(10, Cancel::new());
        queue.assert(&[], 0);
        assert_eq!(queue.tasks.len(), 0);

        let response_send = queue.enqueue(DESC3).unwrap().unwrap();
        queue.assert(&[DESC3], 3);
        assert_eq!(queue.tasks.len(), 1);

        assert_matches!(response_send.send(Bytes::from_static(b"spam")), Ok(()));
        assert_eq!(
            queue.dequeue().await,
            Some((DESC3, Ok(Bytes::from_static(b"spam")))),
        );
        queue.assert(&[], 0);
        assert_eq!(queue.tasks.len(), 0);
    }

    #[tokio::test]
    async fn inner() {
        let mut inner = Inner::new(10);
        inner.assert(&[], 0);
        assert_eq!(inner.can_insert(DESC10), Ok(true));
        assert_eq!(inner.can_insert(DESC11), Err(Full));

        inner.insert(DESC4, Cancel::new());
        inner.assert(&[DESC4], 4);
        assert_eq!(inner.can_insert(DESC4), Ok(false));
        assert_eq!(inner.can_insert(DESC6), Ok(true));
        assert_eq!(inner.can_insert(DESC7), Err(Full));

        inner.insert(DESC2, Cancel::new());
        inner.assert(&[DESC2, DESC4], 6);

        assert_matches!(inner.remove(DESC4), Some(_));
        inner.assert(&[DESC2], 2);
        for _ in 0..3 {
            assert_matches!(inner.remove(DESC4), None);
            inner.assert(&[DESC2], 2);
        }

        assert_matches!(inner.remove(DESC2), Some(_));
        inner.assert(&[], 0);
        for _ in 0..3 {
            assert_matches!(inner.remove(DESC2), None);
            inner.assert(&[], 0);
        }
    }
}
