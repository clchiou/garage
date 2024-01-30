use std::cmp;
use std::collections::BTreeSet;
use std::mem;
use std::time::Duration;

use bytes::Bytes;
use snafu::prelude::*;
use tokio::time::Instant;

use g1_base::collections::{HashBasedTable, NaiveHashBiGraph};
use g1_base::iter::IteratorExt;

use bittorrent_base::{Dimension, PieceIndex};
use bittorrent_manager::{Endpoint, Update};
use bittorrent_peer::Possession;

use crate::bitfield::{Bitfield, BitfieldExt};

// TODO: At the moment, we prioritize the ease of implementation over efficiency.

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub(crate) enum Error {
    #[snafu(display("invalid bitfield: {bitfield:?}"))]
    InvalidBitfield { bitfield: Bytes },
    #[snafu(display("invalid piece index: {piece:?}"))]
    InvalidPieceIndex { piece: PieceIndex },
}

#[derive(Debug)]
pub(crate) struct Scheduler {
    dim: Dimension,

    peer_pieces: NaiveHashBiGraph<Endpoint, PieceIndex>,
    schedule: Vec<PieceIndex>,

    assignments: NaiveHashBiGraph<Endpoint, PieceIndex>,
    max_assignments: usize,
    max_replicates: usize,

    updated: BTreeSet<Endpoint>,

    // In case of errors, where the request is either cancelled or times out, we apply a backoff.
    backoffs: HashBasedTable<Endpoint, PieceIndex, Backoff>,
    backoff_base: Duration,
}

#[derive(Debug)]
struct Backoff {
    // deadline = now + backoff_base * pow(2, num_errors - 1) if num_errors > 0
    deadline: Instant,
    num_errors: u32,
}

impl Scheduler {
    pub(crate) fn new(dim: Dimension, self_pieces: &Bitfield) -> Self {
        Self {
            dim,

            peer_pieces: NaiveHashBiGraph::new(),
            schedule: self_pieces.iter_zeros().map(PieceIndex::from).collect(),

            assignments: NaiveHashBiGraph::new(),
            max_assignments: *crate::max_assignments(),
            max_replicates: *crate::max_replicates(),

            updated: BTreeSet::new(),

            backoffs: HashBasedTable::new(),
            backoff_base: *crate::backoff_base(),
        }
    }

    //
    // Scheduler Logic
    //
    // NOTE: I am not sure if this is a bad idea, but currently, once a `(peer, piece)` pair is
    // scheduled, it will not be replaced even if later a "better" pair emerges.
    //

    pub(crate) fn is_idle(&self) -> bool {
        !self.schedule.is_empty() && self.assignments.is_empty()
    }

    /// Sorts the schedule by rarest-first.
    ///
    /// NOTE: You must call this whenever `peer_pieces` is updated.
    fn sort_schedule(&mut self) {
        self.schedule.sort_by_key(|&piece| {
            self.peer_pieces
                .inverse_get(piece)
                .map(|peers| peers.len())
                .unwrap_or(0)
        })
    }

    /// Sorts peers by fewest ownerships first.
    ///
    /// I do not know if this is a good idea, but when scheduling peers, starting with peers who
    /// own fewer pieces could potentially distribute the load more broadly.
    fn sort_peers(&self, mut peers: Vec<Endpoint>) -> Vec<Endpoint> {
        peers.sort_by_key(|&peer| {
            self.peer_pieces
                .get(peer)
                .map(|pieces| pieces.len())
                .unwrap_or(0)
        });
        peers
    }

    /// Sorts piece indexes according to the schedule.
    ///
    /// NOTE: This filters out piece indexes that are not in the schedule and returns the
    /// corresponding schedule index, not the piece indexes.
    fn sort_pieces(&self, pieces: impl IntoIterator<Item = PieceIndex>) -> Vec<usize> {
        pieces
            .into_iter()
            .filter_map(|piece| self.position(piece))
            .collect_then_sort()
    }

    pub(crate) fn schedule(&mut self, now: Instant) {
        // TODO: At the moment, schedule-all-peers seems to be equivalent to schedule-all-pieces.
        // Should we explicitly define/provide this property?
        self.schedule_peers(self.peer_pieces.keys().collect::<Vec<_>>(), now);
    }

    fn schedule_peers(&mut self, peers: Vec<Endpoint>, now: Instant) {
        for peer in self.sort_peers(peers) {
            self.schedule_peer(peer, now);
        }
    }

    fn schedule_peer(&mut self, peer: Endpoint, now: Instant) {
        let pieces: Vec<_> = self
            .schedule
            .iter()
            .copied()
            .filter(|&piece| self.may_assign_to(peer, piece, now))
            .take(
                self.max_assignments
                    .saturating_sub(self.num_assignments(peer)),
            )
            .collect();
        for piece in pieces {
            assert!(self.assignments.insert(peer, piece));
            self.updated.insert(peer);
        }
    }

    fn schedule_pieces(&mut self, pieces: impl IntoIterator<Item = PieceIndex>, now: Instant) {
        for i in self.sort_pieces(pieces) {
            self.schedule_piece(self.schedule[i], now);
        }
    }

    fn schedule_piece(&mut self, piece: PieceIndex, now: Instant) {
        let peers = match self.peer_pieces.inverse_get(piece) {
            Some(peers) => peers,
            None => return,
        };
        let peers = self.sort_peers(
            peers
                .iter()
                .copied()
                .filter(|&peer| self.may_assign_to(peer, piece, now))
                .collect(),
        );
        let n = self
            .max_replicates
            .saturating_sub(self.num_replicates(piece));
        for &peer in &peers[0..cmp::min(n, peers.len())] {
            assert!(self.assignments.insert(peer, piece));
            self.updated.insert(peer);
        }
    }

    fn may_assign_to(&self, peer: Endpoint, piece: PieceIndex, now: Instant) -> bool {
        if !self.peer_pieces.contains(peer, piece) {
            return false;
        }

        if self.assignments.contains(peer, piece) {
            return false;
        }

        if self.num_assignments(peer) >= self.max_assignments {
            return false;
        }

        if self.num_replicates(piece) >= self.max_replicates {
            return false;
        }

        if self
            .backoffs
            .get(&peer, &piece)
            .map(|backoff| !backoff.is_expired(now))
            .unwrap_or(false)
        {
            return false;
        }

        true
    }

    //
    // Schedule
    //

    pub(crate) fn is_completed(&self) -> bool {
        self.schedule.is_empty()
    }

    pub(crate) fn len(&self) -> usize {
        self.schedule.len()
    }

    fn position(&self, piece: PieceIndex) -> Option<usize> {
        self.schedule.iter().position(|&p| p == piece)
    }

    //
    // Assignments
    //

    pub(crate) fn assignments(&self, peer: Endpoint) -> Option<Vec<PieceIndex>> {
        self.assignments.get(peer).map(|pieces| {
            pieces
                .iter()
                .copied()
                .collect_then_sort_by_key(|&piece| self.position(piece).unwrap())
        })
    }

    fn num_assignments(&self, peer: Endpoint) -> usize {
        self.assignments(peer)
            .map(|pieces| pieces.len())
            .unwrap_or(0)
    }

    fn num_replicates(&self, piece: PieceIndex) -> usize {
        self.assignments
            .inverse_get(piece)
            .map(|peers| peers.len())
            .unwrap_or(0)
    }

    /// Assigns the piece to this peer.
    ///
    /// NOTE: This bypasses the `max_assignments` and `max_replicates` checks.
    ///
    /// Currently, `Scheduler` has only one shared priority queue.  Consequently, the explicitly
    /// assigned pair `(peer, piece)` does not receive higher priority for the given peer.
    ///
    /// TODO: Should we consider implementing per-peer priority queues?
    pub(crate) fn assign(&mut self, peer: Endpoint, piece: PieceIndex) {
        if self.position(piece).is_some() && self.assignments.insert(peer, piece) {
            self.updated.insert(peer);
        }
    }

    pub(crate) fn set_max_assignments(&mut self, max_assignments: usize) {
        assert!(max_assignments > 0);
        self.max_assignments = max_assignments;
    }

    pub(crate) fn set_max_replicates(&mut self, max_replicates: usize) {
        assert!(max_replicates > 0);
        self.max_replicates = max_replicates;
    }

    pub(crate) fn take_updated(&mut self) -> BTreeSet<Endpoint> {
        mem::take(&mut self.updated)
    }

    //
    // Backoff
    //

    /// Returns the nearest non-expired backoff deadline.
    pub(crate) fn next_backoff(&self, now: Instant) -> Option<Instant> {
        self.backoffs
            .values()
            .filter_map(|backoff| (!backoff.is_expired(now)).then_some(backoff.deadline))
            .min()
    }

    pub(crate) fn remove_expired_backoffs(&mut self, now: Instant) {
        let expired: Vec<_> = self
            .backoffs
            .iter()
            .filter_map(|(&peer, &piece, backoff)| backoff.is_expired(now).then_some((peer, piece)))
            .collect();
        for (peer, piece) in &expired {
            self.backoffs.remove(peer, piece);
        }
        self.schedule_peers(expired.into_iter().map(|(peer, _)| peer).collect(), now);
    }

    //
    // Callbacks
    //

    pub(crate) fn notify_peer_update(&mut self, peer: Endpoint, update: Update) {
        match update {
            Update::Start => {
                // We defer the `schedule_peer` call until we receive `Possession` from the peer.
            }
            Update::Stop => {
                self.peer_pieces.remove_key(peer);
                self.sort_schedule();

                let pieces = self.assignments.remove_key(peer);
                self.backoffs.remove_row(&peer);

                if let Some(pieces) = pieces {
                    self.schedule_pieces(pieces, Instant::now());
                }
            }
        }
    }

    pub(crate) fn notify_possession(
        &mut self,
        peer: Endpoint,
        possession: Possession,
    ) -> Result<(), Error> {
        // I am not sure if this is a bad idea, but currently, when peers lose ownership (which I
        // believe is very rare if not impossible), `notify_possession` does not remove their
        // assigned pieces.
        match possession {
            Possession::Bitfield(bitfield) => {
                let bitfield = Bitfield::from_bytes(&bitfield, self.dim.num_pieces).context(
                    InvalidBitfieldSnafu {
                        bitfield: bitfield.clone(),
                    },
                )?;
                self.peer_pieces.remove_key(peer);
                for piece in bitfield.iter_ones() {
                    self.peer_pieces.insert(peer, piece.into());
                }
            }
            Possession::Have(piece) => {
                let piece = self
                    .dim
                    .check_piece_index(piece)
                    .context(InvalidPieceIndexSnafu { piece })?;
                self.peer_pieces.insert(peer, piece);
            }
            Possession::HaveAll => {
                for piece in 0..self.dim.num_pieces {
                    self.peer_pieces.insert(peer, piece.into());
                }
            }
            Possession::HaveNone => {
                self.peer_pieces.remove_key(peer);
            }
        }
        self.sort_schedule();
        self.schedule_peer(peer, Instant::now());
        Ok(())
    }

    pub(crate) fn notify_response_error(&mut self, peer: Endpoint, piece: PieceIndex) {
        if !self.assignments.remove(peer, piece) {
            return;
        }

        let now = Instant::now();

        self.backoffs
            .get_or_insert_with(peer, piece, || Backoff::new(now))
            .increment(now, self.backoff_base);

        self.schedule_peer(peer, now);
        self.schedule_piece(piece, now);
    }

    pub(crate) fn notify_verified(&mut self, piece: PieceIndex) {
        let i = match self.position(piece) {
            Some(i) => i,
            None => return,
        };

        self.schedule.remove(i);
        let peers = self.assignments.remove_value(piece);
        self.backoffs.remove_column(&piece);

        if let Some(peers) = peers {
            self.schedule_peers(peers.into_iter().collect(), Instant::now());
        }
    }
}

impl Backoff {
    fn new(now: Instant) -> Self {
        Self {
            deadline: now,
            num_errors: 0,
        }
    }

    fn is_expired(&self, now: Instant) -> bool {
        self.deadline <= now
    }

    fn increment(&mut self, now: Instant, backoff_base: Duration) {
        let backoff = cmp::min(
            backoff_base.saturating_mul(2u32.saturating_pow(self.num_errors)),
            // It is unlikely to make a difference to back off for longer than an hour.
            Duration::from_secs(3600),
        );
        self.deadline = now + backoff;
        self.num_errors += 1;
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl Scheduler {
        pub fn assert_invariant(&self) {
            assert!(self
                .assignments
                .keys()
                .all(|peer| self.num_assignments(peer) <= self.max_assignments));
            assert!(self
                .assignments
                .values()
                .all(|piece| self.num_replicates(piece) <= self.max_replicates));
            assert!(self
                .assignments
                .iter()
                .all(|(peer, piece)| self.peer_pieces.contains(peer, piece)));
        }

        pub fn assert_peer_pieces<const N: usize>(&self, expect: [(Endpoint, usize); N]) {
            assert_eq!(
                self.peer_pieces,
                expect
                    .into_iter()
                    .map(|(peer, piece)| (peer, piece.into()))
                    .collect(),
            );
        }

        pub fn assert_schedule<const N: usize>(&self, expect: [usize; N]) {
            assert!(self
                .schedule
                .iter()
                .copied()
                .eq(expect.into_iter().map(PieceIndex::from)));
        }

        pub fn assert_assignments<const N: usize>(&self, expect: [(Endpoint, usize); N]) {
            assert_eq!(
                self.assignments,
                expect
                    .into_iter()
                    .map(|(peer, piece)| (peer, piece.into()))
                    .collect(),
            );
        }

        pub fn assert_updated<const N: usize>(&self, expect: [Endpoint; N]) {
            assert!(self.updated.iter().copied().eq(expect.into_iter()));
        }

        pub fn assert_backoffs<const N: usize>(
            &self,
            mut expect: [(Endpoint, usize, Instant, u32); N],
        ) {
            expect.sort();
            assert_eq!(
                self.backoffs
                    .iter()
                    .map(|(&peer, &piece, backoff)| (
                        peer,
                        usize::from(piece),
                        backoff.deadline,
                        backoff.num_errors,
                    ))
                    .collect_then_sort(),
                expect,
            );
        }
    }

    impl Backoff {
        pub fn assert_eq(&self, deadline: Instant, num_errors: u32) {
            assert_eq!(self.deadline, deadline);
            assert_eq!(self.num_errors, num_errors);
        }
    }
}

#[cfg(test)]
mod tests {
    use bitvec::prelude::*;

    use super::*;

    macro_rules! bf {
        ($value:expr; $len:expr) => {
            bits![u8, Msb0; $value; $len]
        };
        ($($value:expr),* $(,)?) => {
            bits![u8, Msb0; $($value),*]
        };
    }

    fn ep(endpoint: &str) -> Endpoint {
        endpoint.parse().unwrap()
    }

    #[test]
    fn new() {
        let dim = Dimension::new(2, 4, 7, 2);

        let scheduler = Scheduler::new(dim.clone(), bf![0; 2]);
        scheduler.assert_schedule([0, 1]);
        scheduler.assert_assignments([]);
        scheduler.assert_backoffs([]);
        assert_eq!(scheduler.is_completed(), false);

        let scheduler = Scheduler::new(dim.clone(), bf![0, 1]);
        scheduler.assert_schedule([0]);

        let scheduler = Scheduler::new(dim.clone(), bf![1, 0]);
        scheduler.assert_schedule([1]);

        let scheduler = Scheduler::new(dim.clone(), bf![1; 2]);
        scheduler.assert_schedule([]);
        assert_eq!(scheduler.is_completed(), true);
    }

    #[test]
    fn sort_schedule() {
        let p0 = ep("127.0.0.1:8000");
        let p1 = ep("127.0.0.1:8001");

        let mut scheduler = Scheduler::new(Dimension::new(3, 1, 3, 1), bf![0; 3]);
        scheduler.assert_schedule([0, 1, 2]);

        scheduler.peer_pieces.insert(p0, 1.into());
        scheduler.peer_pieces.insert(p1, 0.into());
        scheduler.peer_pieces.insert(p1, 1.into());
        scheduler.sort_schedule();
        scheduler.assert_schedule([2, 0, 1]);
    }

    #[test]
    fn sort_peers() {
        let p0 = ep("127.0.0.1:8000");
        let p1 = ep("127.0.0.1:8001");
        let mut scheduler = Scheduler::new(Dimension::new(3, 1, 3, 1), bf![0; 3]);

        assert_eq!(scheduler.sort_peers(vec![p0, p1]), vec![p0, p1]);

        scheduler.peer_pieces.insert(p0, 0.into());
        assert_eq!(scheduler.sort_peers(vec![p0, p1]), vec![p1, p0]);

        scheduler.peer_pieces.insert(p1, 0.into());
        scheduler.peer_pieces.insert(p1, 1.into());
        assert_eq!(scheduler.sort_peers(vec![p0, p1]), vec![p0, p1]);
    }

    #[test]
    fn sort_pieces() {
        let p0 = PieceIndex(0);
        let p1 = PieceIndex(1);
        let p2 = PieceIndex(2);

        let mut scheduler = Scheduler::new(Dimension::new(3, 1, 3, 1), bf![0, 1, 0]);
        scheduler.assert_schedule([0, 2]);

        assert_eq!(scheduler.sort_pieces([p0, p1, p2]), vec![0, 1]);
        assert_eq!(scheduler.sort_pieces([p2, p1, p0]), vec![0, 1]);

        scheduler.schedule.swap(0, 1);
        assert_eq!(scheduler.sort_pieces([p0, p1, p2]), vec![0, 1]);
        assert_eq!(scheduler.sort_pieces([p2, p1, p0]), vec![0, 1]);

        let mut scheduler = Scheduler::new(Dimension::new(3, 1, 3, 1), bf![0; 3]);
        scheduler.schedule.swap(0, 1);
        scheduler.assert_schedule([1, 0, 2]);

        assert_eq!(scheduler.sort_pieces([p0, p1, p2]), vec![0, 1, 2]);
        assert_eq!(scheduler.sort_pieces([p2, p1, p0]), vec![0, 1, 2]);
    }

    #[test]
    fn schedule() {
        let now = Instant::now();
        let p0 = ep("127.0.0.1:8000");
        let p1 = ep("127.0.0.1:8001");
        let p2 = ep("127.0.0.1:8002");
        let p3 = ep("127.0.0.1:8003");
        let p4 = ep("127.0.0.1:8004");

        let mut scheduler = Scheduler::new(Dimension::new(3, 1, 3, 1), bf![0; 3]);
        scheduler.set_max_assignments(2);
        scheduler.set_max_replicates(1);

        scheduler.peer_pieces.insert(p0, 0.into());
        scheduler.peer_pieces.insert(p0, 1.into());
        scheduler.peer_pieces.insert(p0, 2.into());
        scheduler.peer_pieces.insert(p1, 0.into());
        scheduler.peer_pieces.insert(p1, 1.into());
        scheduler.peer_pieces.insert(p2, 0.into());
        scheduler.sort_schedule();
        scheduler.assert_schedule([2, 1, 0]);

        // Test schedule-all-peers.
        for _ in 0..3 {
            scheduler.schedule(now);
            scheduler.assert_assignments([(p0, 2), (p1, 1), (p2, 0)]);
            scheduler.assert_invariant();
        }

        // Test schedule-all-pieces.
        scheduler.assignments.clear();
        for _ in 0..3 {
            scheduler.schedule_pieces([2.into(), 0.into(), 1.into()], now);
            scheduler.assert_assignments([(p0, 2), (p1, 1), (p2, 0)]);
            scheduler.assert_invariant();
        }

        let mut scheduler = Scheduler::new(Dimension::new(7, 1, 7, 1), bf![0; 7]);
        scheduler.set_max_assignments(3);
        scheduler.set_max_replicates(4);
        for (peer, piece) in [p0, p1, p2, p3, p4]
            .into_iter()
            .cycle()
            .zip((0..7).into_iter().cycle())
            .take(5 * 7)
        {
            scheduler.peer_pieces.insert(peer, piece.into());
            scheduler.sort_schedule();
            scheduler.schedule(now);
            scheduler.assert_invariant();
        }
    }

    #[test]
    fn schedule_peer() {
        let now = Instant::now();
        let p0 = ep("127.0.0.1:8000");
        let p1 = ep("127.0.0.1:8001");

        let mut scheduler = Scheduler::new(Dimension::new(3, 1, 3, 1), bf![0; 3]);
        scheduler.set_max_assignments(2);
        scheduler.set_max_replicates(1);
        scheduler.assert_assignments([]);
        scheduler.assert_updated([]);

        scheduler.schedule_peer(p0, now);
        scheduler.assert_assignments([]);
        scheduler.assert_updated([]);

        scheduler.peer_pieces.insert(p0, 0.into());
        for _ in 0..3 {
            scheduler.schedule_peer(p0, now);
            scheduler.assert_assignments([(p0, 0)]);
            scheduler.assert_updated([p0]);
        }

        scheduler.peer_pieces.insert(p0, 1.into());
        scheduler.assignments.clear();
        scheduler.updated.clear();
        for _ in 0..3 {
            scheduler.schedule_peer(p0, now);
            scheduler.assert_assignments([(p0, 0), (p0, 1)]);
            scheduler.assert_updated([p0]);
        }

        scheduler.peer_pieces.insert(p0, 2.into());
        scheduler.assignments.clear();
        scheduler.updated.clear();
        for _ in 0..3 {
            scheduler.schedule_peer(p0, now);
            scheduler.assert_assignments([(p0, 0), (p0, 1)]);
            scheduler.assert_updated([p0]);
        }

        scheduler.schedule.swap(0, 2);
        scheduler.assignments.clear();
        scheduler.updated.clear();
        for _ in 0..3 {
            scheduler.schedule_peer(p0, now);
            scheduler.assert_assignments([(p0, 1), (p0, 2)]);
            scheduler.assert_updated([p0]);
        }

        scheduler.assignments.clear();
        scheduler.assignments.insert(p1, 1.into());
        scheduler.updated.clear();
        for _ in 0..3 {
            scheduler.schedule_peer(p0, now);
            scheduler.assert_assignments([(p0, 0), (p0, 2), (p1, 1)]);
            scheduler.assert_updated([p0]);
        }

        scheduler.assignments.clear();
        scheduler.updated.clear();
        scheduler
            .backoffs
            .get_or_insert_with(p0, 0.into(), || Backoff::new(now))
            .increment(now, scheduler.backoff_base);
        scheduler
            .backoffs
            .get_or_insert_with(p0, 1.into(), || Backoff::new(now))
            .increment(now, scheduler.backoff_base);
        for _ in 0..3 {
            scheduler.schedule_peer(p0, now);
            scheduler.assert_assignments([(p0, 2)]);
            scheduler.assert_updated([p0]);
        }
    }

    #[test]
    fn schedule_piece() {
        let now = Instant::now();
        let p0 = ep("127.0.0.1:8000");
        let p1 = ep("127.0.0.1:8001");
        let p2 = ep("127.0.0.1:8002");

        let mut scheduler = Scheduler::new(Dimension::new(3, 1, 3, 1), bf![0; 3]);
        scheduler.set_max_assignments(1);
        scheduler.set_max_replicates(2);
        scheduler.assert_assignments([]);
        scheduler.assert_updated([]);

        for _ in 0..3 {
            scheduler.schedule_piece(0.into(), now);
            scheduler.assert_assignments([]);
            scheduler.assert_updated([]);
        }

        scheduler.peer_pieces.insert(p0, 0.into());
        for _ in 0..3 {
            scheduler.schedule_piece(0.into(), now);
            scheduler.assert_assignments([(p0, 0)]);
            scheduler.assert_updated([p0]);
        }

        scheduler.peer_pieces.insert(p1, 0.into());
        scheduler.assignments.clear();
        scheduler.updated.clear();
        for _ in 0..3 {
            scheduler.schedule_piece(0.into(), now);
            scheduler.assert_assignments([(p0, 0), (p1, 0)]);
            scheduler.assert_updated([p0, p1]);
        }

        scheduler.peer_pieces.insert(p2, 0.into());
        // Make `p2` less preferred by `sort_peers`.
        scheduler.peer_pieces.insert(p2, 1.into());
        scheduler.assignments.clear();
        scheduler.updated.clear();
        for _ in 0..3 {
            scheduler.schedule_piece(0.into(), now);
            scheduler.assert_assignments([(p0, 0), (p1, 0)]);
            scheduler.assert_updated([p0, p1]);
        }

        // Make `p0` less preferred by `sort_peers`.
        scheduler.peer_pieces.insert(p0, 1.into());
        scheduler.peer_pieces.remove(p2, 1.into());
        scheduler.assignments.clear();
        scheduler.updated.clear();
        for _ in 0..3 {
            scheduler.schedule_piece(0.into(), now);
            scheduler.assert_assignments([(p1, 0), (p2, 0)]);
            scheduler.assert_updated([p1, p2]);
        }

        scheduler.assignments.clear();
        scheduler.assignments.insert(p0, 1.into());
        scheduler.assignments.insert(p1, 1.into());
        scheduler.updated.clear();
        for _ in 0..3 {
            scheduler.schedule_piece(0.into(), now);
            scheduler.assert_assignments([(p2, 0), (p0, 1), (p1, 1)]);
            scheduler.assert_updated([p2]);
        }
    }

    #[test]
    fn may_assign_to() {
        let now = Instant::now();
        let p0 = ep("127.0.0.1:8000");
        let p1 = ep("127.0.0.1:8001");
        let new_scheduler = || {
            let mut scheduler = Scheduler::new(Dimension::new(3, 1, 3, 1), bf![0; 3]);
            scheduler.peer_pieces.insert(p0, 0.into());
            scheduler.set_max_assignments(1);
            scheduler.set_max_replicates(1);
            scheduler
        };

        let mut scheduler = new_scheduler();
        assert_eq!(scheduler.may_assign_to(p0, 0.into(), now), true);
        assert_eq!(scheduler.may_assign_to(p0, 1.into(), now), false);
        assert_eq!(scheduler.may_assign_to(p1, 0.into(), now), false);

        scheduler.assignments.insert(p0, 0.into());
        assert_eq!(scheduler.may_assign_to(p0, 0.into(), now), false);

        let mut scheduler = new_scheduler();
        scheduler.assignments.insert(p0, 1.into());
        assert_eq!(scheduler.may_assign_to(p0, 0.into(), now), false);

        let mut scheduler = new_scheduler();
        scheduler.assignments.insert(p1, 0.into());
        assert_eq!(scheduler.may_assign_to(p0, 0.into(), now), false);

        let mut scheduler = new_scheduler();
        let t1 = now + scheduler.backoff_base;
        scheduler
            .backoffs
            .get_or_insert_with(p0, 0.into(), || Backoff::new(now))
            .increment(now, scheduler.backoff_base);
        assert_eq!(scheduler.may_assign_to(p0, 0.into(), now), false);
        assert_eq!(scheduler.may_assign_to(p0, 0.into(), t1), true);
    }

    #[test]
    fn assignments() {
        let p0 = ep("127.0.0.1:8000");
        let p1 = ep("127.0.0.1:8001");

        let mut scheduler = Scheduler::new(Dimension::new(3, 1, 3, 1), bf![0; 3]);
        scheduler.assert_schedule([0, 1, 2]);
        scheduler.assert_assignments([]);
        assert_eq!(scheduler.assignments(p0), None);
        assert_eq!(scheduler.assignments(p1), None);

        assert_eq!(scheduler.num_assignments(p0), 0);
        assert_eq!(scheduler.num_assignments(p1), 0);
        assert_eq!(scheduler.num_replicates(0.into()), 0);
        assert_eq!(scheduler.num_replicates(1.into()), 0);
        assert_eq!(scheduler.num_replicates(2.into()), 0);

        scheduler.assignments.insert(p0, 0.into());
        scheduler.assignments.insert(p0, 1.into());
        scheduler.assignments.insert(p0, 2.into());
        scheduler.assignments.insert(p1, 0.into());
        scheduler.assignments.insert(p1, 2.into());
        scheduler.assert_assignments([(p0, 0), (p0, 1), (p0, 2), (p1, 0), (p1, 2)]);
        assert_eq!(
            scheduler.assignments(p0),
            Some(vec![0.into(), 1.into(), 2.into()]),
        );
        assert_eq!(scheduler.assignments(p1), Some(vec![0.into(), 2.into()]));

        assert_eq!(scheduler.num_assignments(p0), 3);
        assert_eq!(scheduler.num_assignments(p1), 2);
        assert_eq!(scheduler.num_replicates(0.into()), 2);
        assert_eq!(scheduler.num_replicates(1.into()), 1);
        assert_eq!(scheduler.num_replicates(2.into()), 2);

        scheduler.schedule.swap(0, 1);
        assert_eq!(
            scheduler.assignments(p0),
            Some(vec![1.into(), 0.into(), 2.into()]),
        );
        assert_eq!(scheduler.assignments(p1), Some(vec![0.into(), 2.into()]));
    }

    #[test]
    fn next_backoff() {
        let p0 = ep("127.0.0.1:8000");
        let p1 = ep("127.0.0.1:8001");

        let mut scheduler = Scheduler::new(Dimension::new(1, 1, 1, 1), bf![0]);
        scheduler.assert_backoffs([]);

        let t0 = Instant::now();
        let t1 = t0 + scheduler.backoff_base;
        let t2 = t1 + scheduler.backoff_base;

        assert_eq!(scheduler.next_backoff(t0), None);
        assert_eq!(scheduler.next_backoff(t1), None);
        assert_eq!(scheduler.next_backoff(t2), None);

        scheduler
            .backoffs
            .get_or_insert_with(p0, 0.into(), || Backoff::new(t0))
            .increment(t0, scheduler.backoff_base);
        scheduler.assert_backoffs([(p0, 0, t1, 1)]);
        assert_eq!(scheduler.next_backoff(t0), Some(t1));
        assert_eq!(scheduler.next_backoff(t1), None);
        assert_eq!(scheduler.next_backoff(t2), None);

        scheduler
            .backoffs
            .get_or_insert_with(p1, 1.into(), || Backoff::new(t1))
            .increment(t1, scheduler.backoff_base);
        scheduler.assert_backoffs([(p0, 0, t1, 1), (p1, 1, t2, 1)]);
        assert_eq!(scheduler.next_backoff(t0), Some(t1));
        assert_eq!(scheduler.next_backoff(t1), Some(t2));
        assert_eq!(scheduler.next_backoff(t2), None);

        scheduler.backoffs.remove(&p0, &0.into());
        scheduler.assert_backoffs([(p1, 1, t2, 1)]);
        assert_eq!(scheduler.next_backoff(t0), Some(t2));
        assert_eq!(scheduler.next_backoff(t1), Some(t2));
        assert_eq!(scheduler.next_backoff(t2), None);
    }

    #[test]
    fn remove_expired_backoffs() {
        let p0 = ep("127.0.0.1:8000");
        let p1 = ep("127.0.0.1:8001");

        let mut scheduler = Scheduler::new(Dimension::new(3, 1, 3, 1), bf![0; 3]);
        scheduler.set_max_assignments(2);
        scheduler.set_max_replicates(2);
        scheduler.peer_pieces.insert(p0, 0.into());
        scheduler.peer_pieces.insert(p1, 1.into());
        scheduler.peer_pieces.insert(p1, 2.into());
        scheduler.assert_backoffs([]);

        let t0 = Instant::now();
        let t1 = t0 + scheduler.backoff_base;
        let t2 = t1 + scheduler.backoff_base;

        scheduler.remove_expired_backoffs(t0);
        scheduler.assert_assignments([]);
        scheduler.assert_updated([]);
        scheduler.assert_backoffs([]);

        scheduler.backoffs.insert(p0, 0.into(), Backoff::new(t0));
        scheduler.backoffs.insert(p1, 1.into(), Backoff::new(t1));
        scheduler.backoffs.insert(p1, 2.into(), Backoff::new(t2));
        scheduler.assert_backoffs([(p0, 0, t0, 0), (p1, 1, t1, 0), (p1, 2, t2, 0)]);

        for _ in 0..3 {
            scheduler.remove_expired_backoffs(t1);
            scheduler.assert_assignments([(p0, 0), (p1, 1)]);
            scheduler.assert_updated([p0, p1]);
            scheduler.assert_backoffs([(p1, 2, t2, 0)]);
        }
    }

    #[test]
    fn notify_peer_update() {
        let p0 = ep("127.0.0.1:8000");
        let p1 = ep("127.0.0.1:8001");

        let mut scheduler = Scheduler::new(Dimension::new(3, 1, 3, 1), bf![0; 3]);
        scheduler.set_max_assignments(2);
        scheduler.set_max_replicates(2);
        scheduler.peer_pieces.insert(p1, 0.into());
        scheduler.assignments.insert(p0, 0.into());
        scheduler
            .backoffs
            .insert(p0, 0.into(), Backoff::new(Instant::now()));
        scheduler.assert_assignments([(p0, 0)]);
        assert_eq!(scheduler.backoffs.is_empty(), false);

        scheduler.notify_peer_update(p1, Update::Start);
        scheduler.assert_assignments([(p0, 0)]);

        scheduler.notify_peer_update(p0, Update::Stop);
        scheduler.assert_assignments([(p1, 0)]);
        scheduler.assert_backoffs([]);
    }

    #[test]
    fn notify_possession() {
        let p0 = ep("127.0.0.1:8000");
        let p1 = ep("127.0.0.1:8001");

        let mut scheduler = Scheduler::new(Dimension::new(3, 1, 3, 1), bf![0; 3]);
        scheduler.set_max_assignments(2);
        scheduler.set_max_replicates(2);
        scheduler.assert_peer_pieces([]);
        scheduler.assert_assignments([]);

        assert_eq!(
            scheduler.notify_possession(p0, Possession::Bitfield(Bytes::from_static(&[]))),
            Err(Error::InvalidBitfield {
                bitfield: Bytes::from_static(&[]),
            }),
        );
        scheduler.assert_peer_pieces([]);
        scheduler.assert_assignments([]);

        assert_eq!(
            scheduler.notify_possession(p0, Possession::Bitfield(Bytes::from_static(&[0x10]))),
            Err(Error::InvalidBitfield {
                bitfield: Bytes::from_static(&[0x10]),
            }),
        );
        scheduler.assert_peer_pieces([]);
        scheduler.assert_assignments([]);

        assert_eq!(
            scheduler.notify_possession(p0, Possession::Have(4.into())),
            Err(Error::InvalidPieceIndex { piece: 4.into() }),
        );
        scheduler.assert_peer_pieces([]);
        scheduler.assert_assignments([]);

        scheduler.assert_schedule([0, 1, 2]);

        assert_eq!(
            scheduler.notify_possession(p0, Possession::Bitfield(Bytes::from_static(&[0x80]))),
            Ok(()),
        );
        scheduler.assert_schedule([1, 2, 0]);
        scheduler.assert_peer_pieces([(p0, 0)]);
        scheduler.assert_assignments([(p0, 0)]);

        assert_eq!(
            scheduler.notify_possession(p0, Possession::Have(1.into())),
            Ok(()),
        );
        scheduler.assert_schedule([2, 1, 0]);
        scheduler.assert_peer_pieces([(p0, 0), (p0, 1)]);
        scheduler.assert_assignments([(p0, 0), (p0, 1)]);

        assert_eq!(scheduler.notify_possession(p1, Possession::HaveAll), Ok(()));
        scheduler.assert_schedule([2, 1, 0]);
        scheduler.assert_peer_pieces([(p0, 0), (p0, 1), (p1, 0), (p1, 1), (p1, 2)]);
        scheduler.assert_assignments([(p0, 0), (p0, 1), (p1, 1), (p1, 2)]);

        assert_eq!(
            scheduler.notify_possession(p1, Possession::HaveNone),
            Ok(()),
        );
        scheduler.assert_schedule([2, 1, 0]);
        scheduler.assert_peer_pieces([(p0, 0), (p0, 1)]);
        scheduler.assert_assignments([(p0, 0), (p0, 1), (p1, 1), (p1, 2)]);
    }

    #[tokio::test(start_paused = true)]
    async fn notify_response_error() {
        let now = Instant::now();
        let p0 = ep("127.0.0.1:8000");
        let p1 = ep("127.0.0.1:8001");

        let mut scheduler = Scheduler::new(Dimension::new(3, 1, 3, 1), bf![0; 3]);
        scheduler.peer_pieces.insert(p0, 0.into());
        scheduler.peer_pieces.insert(p0, 1.into());
        scheduler.peer_pieces.insert(p1, 0.into());
        scheduler.assignments.insert(p0, 0.into());
        scheduler.set_max_assignments(2);
        scheduler.set_max_replicates(2);
        scheduler.assert_assignments([(p0, 0)]);
        scheduler.assert_backoffs([]);

        scheduler.notify_response_error(p0, 0.into());
        scheduler.assert_assignments([(p0, 1), (p1, 0)]);
        scheduler.assert_backoffs([(p0, 0, now + scheduler.backoff_base, 1)]);
    }

    #[test]
    fn notify_verified() {
        let p0 = ep("127.0.0.1:8000");
        let p1 = ep("127.0.0.1:8001");

        let mut scheduler = Scheduler::new(Dimension::new(2, 1, 2, 1), bf![0; 2]);
        scheduler.peer_pieces.insert(p0, 0.into());
        scheduler.peer_pieces.insert(p0, 1.into());
        scheduler.assignments.insert(p0, 0.into());
        scheduler
            .backoffs
            .insert(p1, 0.into(), Backoff::new(Instant::now()));
        scheduler.assert_schedule([0, 1]);

        for _ in 0..3 {
            scheduler.notify_verified(0.into());
            scheduler.assert_schedule([1]);
            scheduler.assert_assignments([(p0, 1)]);
            scheduler.assert_backoffs([]);
        }
    }

    #[test]
    fn backoff() {
        let now = Instant::now();

        let mut backoff = Backoff::new(now);
        backoff.assert_eq(now, 0);

        assert_eq!(backoff.is_expired(now - Duration::SECOND), false);
        assert_eq!(backoff.is_expired(now), true);
        assert_eq!(backoff.is_expired(now + Duration::SECOND), true);

        for n in 1..=12 {
            backoff.increment(now, Duration::SECOND);
            backoff.assert_eq(now + Duration::from_secs(1 << (n - 1)), n);
        }

        for n in 13..=16 {
            backoff.increment(now, Duration::SECOND);
            backoff.assert_eq(now + Duration::from_secs(3600), n);
        }
    }
}
