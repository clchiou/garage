use std::collections::hash_map::Entry;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::time::Duration;

use g1_base::collections::{Array, LilVec};
use g1_tokio::time::set::naive::FixedDelaySet;

use bt_base::{BlockRange, ConnId, InfoHash, PeerEndpoint, PieceIndex};
use bt_model::Model;

use super::Schedule;
use super::time::FixedDelaySetExt;

pub(super) struct DownloadState {
    // For any block, the number of `PeerState`s whose `inflights` contain the block equals the
    // number stored in `requests`.
    //
    // We may have multiple connections to the same peer endpoint (one for each torrent), and it
    // seems to make sense to use only one of these connections at any given time.
    window: HashMap<PeerEndpoint, PeerState>,
    requests: HashMap<(InfoHash, PieceIndex), BTreeMap<BlockRange, usize>>,

    paused: HashSet<InfoHash>,

    reject_cooldowns: FixedDelaySet<(ConnId, BlockRange)>,
}

struct PeerState {
    conn_id: ConnId,
    index: PieceIndex,
    inflights: HashSet<BlockRange>,
}

//
// TODO: Make these parameters configurable.
//

/// Number of pieces downloaded concurrently (i.e., the download window).
// TODO: We should consider adjusting it dynamically to maintain the target throughput.
const WINDOW_SIZE: usize = 16;

/// Number of peers we download a piece from.
// TODO: We should consider increasing it dynamically during endgame mode.
const FANOUT: usize = 1;

/// Number of inflight requests sent to a peer.
const INFLIGHT_QUEUE_SIZE: usize = 4;

/// Number of replicated requests (which must not exceed `FANOUT`).
// TODO: We should consider increasing it dynamically during endgame mode.
const REDUNDANCY: usize = 1;

/// Size of our requested blocks.
const BLOCK_SIZE: u64 = 16384;

/// Duration that a `(peer, request)` pair remains in the rejected status.
const REJECT_COOLDOWN: Duration = Duration::from_secs(32);

impl DownloadState {
    pub(super) fn new() -> Self {
        Self {
            window: HashMap::new(),
            requests: HashMap::new(),
            paused: HashSet::new(),
            reject_cooldowns: FixedDelaySet::new(REJECT_COOLDOWN),
        }
    }

    pub(super) fn pause(&mut self, info_hash: InfoHash) -> bool {
        self.paused.insert(info_hash)
    }

    pub(super) fn resume(&mut self, info_hash: InfoHash) -> bool {
        self.paused.remove(&info_hash)
    }

    // TODO: This is inefficient.
    pub(super) fn assign(
        &mut self,
        // We assume the schedule is not recalculated immediately after every model change, and
        // thus we check the model when applying the schedule.
        model: &Model,
        schedule: &Schedule,
    ) -> impl Iterator<Item = ConnId> + use<> {
        let conn_states = model.conn_states();
        let torrents = model.torrents();

        // TODO: This is lame, but since `schedule` is quite long, we artificially limit the
        // traversal to twice the window size.
        let mut schedule = schedule.iter().take(WINDOW_SIZE * 2);

        // TODO: Should `num_assigned_map` be part of `DownloadState`?
        let mut num_assigned_map = <HashMap<_, usize>>::new();
        for peer_state in self.window.values() {
            *num_assigned_map
                .entry((peer_state.conn_id.info_hash(), peer_state.index))
                .or_default() += 1;
        }

        let mut assigned = <LilVec<_, 4>>::new();
        while self.window.len() < WINDOW_SIZE {
            let Some((info_hash, index, conn_pairs)) = schedule.next() else {
                break;
            };

            let Some(torrent) = torrents.get(info_hash.clone()) else {
                continue;
            };

            let index = *index;
            let i = usize::from(index);
            if torrent.self_pieces()[i] {
                continue;
            }

            if self.paused.contains(info_hash) {
                continue;
            }

            let num_assigned = num_assigned_map
                .entry((info_hash.clone(), index))
                .or_default();
            if *num_assigned >= FANOUT {
                continue;
            }

            for candidate in conn_pairs {
                if self.window.contains_key(&candidate.1) {
                    continue;
                }

                if torrent
                    .get(candidate)
                    .is_none_or(|peer_pieces| !peer_pieces[i])
                {
                    continue;
                }

                let conn_id = ConnId::from((info_hash.clone(), *candidate));
                if conn_states
                    .get(&conn_id)
                    .is_none_or(|conn_state| conn_state.peer_choking() || conn_state.snubbing())
                {
                    continue;
                }

                tracing::debug!(%conn_id, ?index, "assign");
                let state = PeerState {
                    conn_id: conn_id.clone(),
                    index,
                    inflights: HashSet::new(),
                };
                assert!(self.window.insert(candidate.1, state).is_none());
                assigned.push(conn_id);
                *num_assigned += 1;

                self.requests
                    .entry((info_hash.clone(), index))
                    .or_insert_with(|| {
                        torrent
                            .layout()
                            .blocks(index, BLOCK_SIZE)
                            .map(|range| (range, 0))
                            .collect()
                    });

                // If `FANOUT > 1`, `window.len()` might exceed `WINDOW_SIZE`, which is okay.
                if *num_assigned >= FANOUT {
                    break;
                }
            }
        }
        if self.window.is_empty() {
            tracing::warn!("download window empty");
        }

        assigned.into_iter()
    }

    pub(super) fn is_assigned(&self, conn_id: &ConnId) -> bool {
        self.window
            .get(&conn_id.peer_endpoint())
            .is_some_and(|peer_state| &peer_state.conn_id == conn_id)
    }

    // NOTE: I am not sure if this is a good idea, but it modifies the state before returning the
    // pending requests.  In other words, the state has been changed regardless of whether the
    // caller sends the requests.
    pub(super) fn queue_requests(
        &mut self,
        conn_id: &ConnId,
    ) -> Option<impl Iterator<Item = BlockRange>> {
        let peer_state = self.window.get_mut(&conn_id.peer_endpoint())?;
        if &peer_state.conn_id != conn_id {
            return None;
        }

        let requests = self
            .requests
            .get_mut(&(conn_id.info_hash(), peer_state.index))
            .expect("requests");
        let mut requests = requests.iter_mut();

        self.reject_cooldowns.clear_expired();

        let mut pending = <Array<_, INFLIGHT_QUEUE_SIZE>>::new();
        while peer_state.inflights.len() < INFLIGHT_QUEUE_SIZE {
            let Some((block, num_inflights)) = requests.next() else {
                break;
            };

            if *num_inflights >= REDUNDANCY {
                continue;
            }

            if self.reject_cooldowns.contains(&(conn_id.clone(), *block)) {
                continue;
            }

            if !peer_state.inflights.insert(*block) {
                continue;
            }

            *num_inflights += 1;
            pending.push(*block);
        }

        Some(pending.into_iter())
    }

    //
    // State-Change Callbacks
    //

    pub(super) fn recv(
        &mut self,
        conn_id: &ConnId,
        range: BlockRange,
    ) -> Option<(bool, impl Iterator<Item = ConnId> + use<>)> {
        let peer_state = self.window.get_mut(&conn_id.peer_endpoint())?;
        if &peer_state.conn_id != conn_id {
            return None;
        }

        // For simplicity, we ignore any blocks that were not explicitly requested.
        if !peer_state.inflights.remove(&range) {
            return None;
        }

        // Remove request from queue.
        let requests = self
            .requests
            .get_mut(&(conn_id.info_hash(), peer_state.index))
            .expect("requests");
        let num_inflights = requests.remove(&range).expect("request");
        let last = requests.is_empty();

        // Cancel replicated requests.
        let mut cancels = <LilVec<_, FANOUT>>::new();
        for other in self.window.values_mut() {
            if other.conn_id.info_hash == conn_id.info_hash && other.inflights.remove(&range) {
                cancels.push(other.conn_id.clone());
            }
        }
        assert_eq!(cancels.len() + 1, num_inflights);

        //
        // We do not remove `(_, range)` from `reject_cooldowns` in case verification fails and we
        // need to request the blocks again.
        //

        Some((last, cancels.into_iter()))
    }

    // A reject can be either explicit or implicit due to a timeout.
    //
    // If a peer continually rejects our requests, we will snub it and switch to another peer,
    // allowing us to make progress eventually.
    pub(super) fn reject(&mut self, conn_id: &ConnId, range: BlockRange) -> bool {
        let Some(peer_state) = self.window.get_mut(&conn_id.peer_endpoint()) else {
            return false;
        };
        if &peer_state.conn_id != conn_id {
            return false;
        }

        if !peer_state.inflights.remove(&range) {
            return false;
        }

        // Dequeue request.
        let requests = self
            .requests
            .get_mut(&(conn_id.info_hash(), peer_state.index))
            .expect("requests");
        *requests.get_mut(&range).expect("request") -= 1;

        self.reject_cooldowns.insert((conn_id.clone(), range));

        true
    }

    // Call this when a peer chokes us, is snubbed, or disconnects.
    pub(super) fn remove_peer(&mut self, conn_id: &ConnId) -> bool {
        let Entry::Occupied(entry) = self.window.entry(conn_id.peer_endpoint()) else {
            return false;
        };
        if &entry.get().conn_id != conn_id {
            return false;
        }

        let peer_state = entry.remove();

        // Dequeue requests.
        let requests = self
            .requests
            .get_mut(&(conn_id.info_hash(), peer_state.index))
            .expect("requests");
        for range in &peer_state.inflights {
            *requests.get_mut(range).expect("request") -= 1;
        }

        self.reject_cooldowns.remove_peer(conn_id);

        true
    }

    // Call this after downloading a piece, regardless of the verification result.
    pub(super) fn remove_piece(&mut self, info_hash: InfoHash, index: PieceIndex) {
        self.window
            .retain(|_, state| state.conn_id.info_hash != info_hash || state.index != index);
        assert!(self.requests.remove(&(info_hash, index)).is_some());

        //
        // We do not remove `reject_cooldowns` in case verification fails and we need to request
        // the blocks again.
        //
    }

    pub(super) fn remove_torrent(&mut self, info_hash: InfoHash) {
        self.window
            .retain(|_, state| state.conn_id.info_hash != info_hash);
        self.requests.retain(|(hash, _), _| hash != &info_hash);

        self.paused.remove(&info_hash);

        self.reject_cooldowns.remove_torrent(info_hash.clone());
    }
}
