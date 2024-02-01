use std::collections::{
    hash_map::{Entry, OccupiedEntry},
    BTreeMap, BTreeSet, HashMap,
};
use std::ops::{Deref, DerefMut};

use bittorrent_base::{BlockDesc, Dimension, PieceIndex};
use bittorrent_manager::Endpoint;

use crate::progress::Progress;

// Use `BTreeMap` for nicer logging output.
pub(crate) type RecvStats = BTreeMap<Endpoint, u64>;

#[derive(Debug)]
pub(crate) struct Queues {
    dim: Dimension,
    queues: HashMap<PieceIndex, Queue>,
}

#[derive(Debug)]
pub(crate) struct QueueStub<'a>(OccupiedEntry<'a, PieceIndex, Queue>);

#[derive(Debug)]
pub(crate) struct Queue {
    requests: BTreeSet<BlockDesc>,
    progress: Progress,
    recv_stats: RecvStats,
    piece: PieceIndex, // Just for sanity check.
}

impl Queues {
    pub(crate) fn new(dim: Dimension) -> Self {
        Self {
            dim,
            queues: HashMap::new(),
        }
    }

    pub(crate) fn get_mut(&mut self, piece: PieceIndex) -> Option<&mut Queue> {
        self.queues.get_mut(&piece)
    }

    pub(crate) fn get_or_default(&mut self, piece: PieceIndex) -> QueueStub {
        QueueStub(match self.queues.entry(piece) {
            Entry::Occupied(entry) => entry,
            Entry::Vacant(entry) => entry.insert_entry(Queue::new(&self.dim, piece)),
        })
    }

    pub(crate) fn remove_peer(&mut self, peer: Endpoint) {
        for queue in self.queues.values_mut() {
            queue.recv_stats.remove(&peer);
        }
    }
}

impl<'a> QueueStub<'a> {
    pub(crate) fn remove(self) -> RecvStats {
        self.0.remove().recv_stats
    }
}

impl<'a> Deref for QueueStub<'a> {
    type Target = Queue;

    fn deref(&self) -> &Self::Target {
        self.0.get()
    }
}

impl<'a> DerefMut for QueueStub<'a> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        self.0.get_mut()
    }
}

impl Queue {
    fn new(dim: &Dimension, piece: PieceIndex) -> Self {
        Self {
            requests: dim.block_descs(piece).collect(),
            progress: Progress::new(dim, piece),
            recv_stats: RecvStats::new(),
            piece,
        }
    }

    pub(crate) fn pop_request(&mut self) -> Option<BlockDesc> {
        self.requests.pop_first()
    }

    pub(crate) fn push_request(&mut self, request: BlockDesc) {
        assert_eq!(request.0 .0, self.piece);
        self.requests.insert(request);
    }

    pub(crate) fn is_completed(&self) -> bool {
        self.progress.is_completed()
    }

    // NOTE: `block` may or may not be a request that we sent.
    pub(crate) fn add_progress(&mut self, peer: Endpoint, block: BlockDesc) -> u64 {
        assert_eq!(block.0 .0, self.piece);
        let num_recv = self.progress.add(block);
        if num_recv > 0 {
            *self.recv_stats.entry(peer).or_default() += num_recv;
        }
        num_recv
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl Queues {
        pub fn assert_pieces<const N: usize>(&self, expect: [usize; N]) {
            assert!(self
                .queues
                .keys()
                .copied()
                .eq(expect.into_iter().map(PieceIndex::from)));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn queues() {
        let p0: Endpoint = "127.0.0.1:8000".parse().unwrap();

        let mut queues = Queues::new(Dimension::new(3, 1, 3, 1));
        queues.assert_pieces([]);

        let mut q = queues.get_or_default(0.into());
        assert_eq!(q.pop_request(), Some((0, 0, 1).into()));
        assert_eq!(q.is_completed(), false);
        assert_eq!(q.add_progress(p0, (0, 0, 1).into()), 1);
        assert_eq!(q.is_completed(), true);
        assert_eq!(q.add_progress(p0, (0, 0, 1).into()), 0);
        queues.assert_pieces([0]);

        assert_eq!(
            queues.get_or_default(0.into()).remove(),
            RecvStats::from([(p0, 1)]),
        );
        queues.assert_pieces([]);
    }
}
