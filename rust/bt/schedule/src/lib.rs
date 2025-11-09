use std::collections::hash_map::Entry;
use std::collections::{HashMap, HashSet};
use std::ops::ControlFlow;
use std::sync::{Arc, Mutex};

use rand::prelude::*;

use g1_base::sync::MutexExt;
use g1_tokio::task::{self, BoxJoinable, Joinable};

use bt_base::bitfield::BitsliceExt;
use bt_base::{Bitfield, ConnId, ConnPair, InfoHash, PieceIndex};
use bt_model::fold::{self, Closed, Consumer, Fold};
use bt_model::{Model, ModelUpdate, Torrent};
use bt_txrx::download::{Download, Schedule};

// TODO: This is inefficient.
struct SchedulerActor {
    model: Arc<Mutex<Model>>,
    changes: Consumer<HashMap<InfoHash, Change>>,

    sub_scheds: SubSchedules,

    download: Download,
}

pub type SchedulerGuard = BoxJoinable<()>;

// Invariant: Entries must be non-empty and sorted.
struct SubSchedules(HashMap<InfoHash, SubSchedule>);

//
// For `SubSchedule` entries `(index, candidates)`, we maintain the following invariants:
//
// * `self_pieces[index]` must be false.
//
// * `candidates` must be non-empty but unsorted.
//
// * The `SubSchedule` entries themselves are sorted.
//
type SubSchedule = Vec<(PieceIndex, Candidates)>;

type Candidates = Vec<ConnPair>;

trait SubScheduleExt {
    fn get_candidates_mut(&mut self, index: PieceIndex) -> Option<&mut Candidates>;
}

trait CandidatesExt {
    fn insert_candidate(&mut self, candidate: ConnPair) -> bool;

    fn remove_candidate(&mut self, candidate: &ConnPair) -> bool;
}

struct Folder;

// We simply record if `model` has changed; the caller must query `model` to retrieve the current
// value.
#[derive(Default)]
struct Change {
    init_or_remove: bool,
    self_pieces: bool,

    peers: HashSet<ConnId>,
}

//
// For now, we prioritize schedule entries in a very naive way:
//
// * Entries with fewer candidates have higher priority.
//
// * In case of a tie, the entry whose torrent is closer to completion (i.e., has fewer remaining
//   entries) has higher priority.
//
// * If there is still a tie, we use `(info_hash, index)` as the final tiebreaker.
//

fn priority<'a>(
    info_hash: &'a InfoHash,
    sub_sched: &SubSchedule,
    i: usize,
) -> (usize, usize, &'a InfoHash, PieceIndex) {
    let (num_cands, index) = sub_priority(&sub_sched[i]);
    (num_cands, sub_sched.len(), info_hash, index)
}

fn sub_priority(entry: &(PieceIndex, Candidates)) -> (usize, PieceIndex) {
    (entry.1.len(), entry.0)
}

impl Scheduler {
    pub fn spawn(model: Arc<Mutex<Model>>, download: Download) -> (Self, SchedulerGuard) {
        let (changes, fold_guard) = fold::spawn(Folder, model.must_lock().subscribe());

        let (this, scheduler_guard) = Self::spawn_impl(SchedulerActor {
            model,
            changes,
            sub_scheds: SubSchedules::new(),
            download,
        });

        (
            this,
            task::try_fold([scheduler_guard, fold_guard], (), |acc, result| {
                assert!(matches!(acc, Ok(())));
                ControlFlow::Break(result)
            })
            .boxed(),
        )
    }
}

impl Fold for Folder {
    type Value = HashMap<InfoHash, Change>;

    fn fold(&mut self, value: &mut Option<Self::Value>, update: ModelUpdate) {
        fn get(value: &mut Option<HashMap<InfoHash, Change>>, info_hash: InfoHash) -> &mut Change {
            value.get_or_insert_default().entry(info_hash).or_default()
        }

        match update {
            ModelUpdate::InitTorrent(info_hash) | ModelUpdate::RemoveTorrent(info_hash) => {
                get(value, info_hash).init_or_remove = true;
            }
            ModelUpdate::SetSelfPiece(info_hash, _) => {
                get(value, info_hash).self_pieces = true;
            }

            ModelUpdate::InitPeer(conn_id)
            | ModelUpdate::SetPeerPiece(conn_id, _)
            | ModelUpdate::DisconnectPeer(conn_id) => {
                get(value, conn_id.info_hash()).peers.insert(conn_id);
            }

            // Other updates are irrelevant to us.
            _ => {}
        }
    }
}

#[g1_actor::actor(stub(pub, Scheduler, spawn(spawn_impl)))]
impl SchedulerActor {
    // Useful when we initialize the tracker or the DHT client before starting the scheduler.
    #[actor::method(pub, stub(return { let result: () = (); }))]
    async fn scan(&mut self) {
        let mut inserted = false;
        {
            let model = self.model.must_lock();
            for (info_hash, torrent) in model.torrents().iter() {
                if self.sub_scheds.init_torrent(info_hash, torrent) {
                    inserted = true;
                }
            }
        }

        if inserted {
            self.assign().await;
        }
    }

    #[actor::loop_(react = {
        let changes = self.changes.consume();
        match changes {
            Ok(changes) => self.consume_changes(changes).await,
            Err(Closed) => break,
        }
    })]
    async fn consume_changes(&mut self, changes: HashMap<InfoHash, Change>) {
        let mut inserted = false;
        {
            let model = self.model.must_lock();
            let torrents = model.torrents();
            for (info_hash, change) in changes {
                let Some(torrent) = torrents.get(info_hash.clone()) else {
                    self.sub_scheds.remove_torrent(info_hash);
                    continue;
                };

                if change.init_or_remove {
                    if self.sub_scheds.init_torrent(info_hash, torrent) {
                        inserted = true;
                    }
                    continue;
                }

                if change.self_pieces {
                    // NOTE: We assume for now that `self_pieces` is monotonic - bits may be set
                    // but never cleared.  Therefore, we only remove entries from `sub_scheds`, not
                    // insert them.
                    self.sub_scheds.remove_self_have(info_hash, torrent);
                }

                let self_pieces = torrent.self_pieces();
                for conn_id in change.peers {
                    match torrent.get(&conn_id.conn_pair) {
                        Some(peer_pieces) => {
                            if self
                                .sub_scheds
                                .update_peer(conn_id, self_pieces, peer_pieces)
                            {
                                inserted = true;
                            }
                        }
                        None => self.sub_scheds.remove_peer(&conn_id),
                    }
                }
            }
        }

        if inserted {
            self.assign().await;
        }
    }

    async fn assign(&self) {
        if !self.sub_scheds.is_empty() {
            let schedule = self.sub_scheds.merge();
            assert!(!schedule.is_empty());
            self.download.assign(schedule).await;
        }
    }
}

impl SubSchedules {
    fn new() -> Self {
        Self(HashMap::new())
    }

    fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    fn init_torrent(&mut self, info_hash: InfoHash, torrent: &Torrent) -> bool {
        let self_pieces = torrent.self_pieces();

        let mut sub_sched = <HashMap<_, Candidates>>::with_capacity(self_pieces.count_zeros());
        for (conn_pair, peer_pieces) in torrent.iter() {
            for index in peer_pieces.iter_haves() {
                if !self_pieces[usize::from(index)] {
                    // NOTE: We can use `push` since we are not sorting candidates at the moment.
                    sub_sched.entry(index).or_default().push(*conn_pair);
                }
            }
        }

        let sub_sched = sub_sched
            .into_iter()
            .filter(|(_, candidates)| !candidates.is_empty())
            .collect::<SubSchedule>();
        if sub_sched.is_empty() {
            return false;
        }

        self.0
            .entry(info_hash)
            .insert_entry(sub_sched)
            .get_mut()
            .sort_by_key(sub_priority);
        true
    }

    fn remove_self_have(&mut self, info_hash: InfoHash, torrent: &Torrent) {
        let self_pieces = torrent.self_pieces();
        self.remove_if(info_hash, |index, _| self_pieces[usize::from(index)]);
    }

    fn update_peer(
        &mut self,
        conn_id: ConnId,
        self_pieces: &Bitfield,
        peer_pieces: &Bitfield,
    ) -> bool {
        match self.0.entry(conn_id.info_hash()) {
            Entry::Occupied(mut entry) => {
                let sub_sched = entry.get_mut();
                let mut inserted = false;
                for (i, peer_have) in peer_pieces.iter().by_vals().enumerate() {
                    let Some(candidates) = sub_sched.get_candidates_mut(i.into()) else {
                        assert!(self_pieces[i]);
                        continue;
                    };
                    if peer_have {
                        if candidates.insert_candidate(conn_id.conn_pair) {
                            inserted = true;
                        }
                    } else {
                        candidates.remove_candidate(&conn_id.conn_pair);
                    }
                }
                if sub_sched.is_empty() {
                    entry.remove();
                    false
                } else {
                    sub_sched.sort_by_key(sub_priority);
                    inserted
                }
            }
            Entry::Vacant(entry) => {
                let sub_sched = self_pieces
                    .iter_have_nots()
                    .filter(|index| peer_pieces[usize::from(*index)])
                    .map(|index| (index, vec![conn_id.conn_pair]))
                    .collect::<SubSchedule>();
                if sub_sched.is_empty() {
                    return false;
                }
                entry.insert(sub_sched).sort_by_key(sub_priority);
                true
            }
        }
    }

    fn remove_peer(&mut self, conn_id: &ConnId) {
        self.remove_if(conn_id.info_hash(), |_, candidates| {
            candidates.remove_candidate(&conn_id.conn_pair);
            candidates.is_empty()
        });
    }

    // NOTE: The caller must guarantee that `f` does not insert any candidates.
    fn remove_if<F>(&mut self, info_hash: InfoHash, mut f: F)
    where
        F: FnMut(PieceIndex, &mut Candidates) -> bool,
    {
        let Entry::Occupied(mut entry) = self.0.entry(info_hash) else {
            // We can simply return, since `f` does not insert.
            return;
        };
        let sub_sched = entry.get_mut();
        sub_sched.retain_mut(|(index, candidates)| !f(*index, candidates));
        if sub_sched.is_empty() {
            entry.remove();
        } else {
            sub_sched.sort_by_key(sub_priority);
        }
    }

    fn remove_torrent(&mut self, info_hash: InfoHash) {
        self.0.remove(&info_hash);
    }

    fn merge(&self) -> Schedule {
        let mut schedule =
            Schedule::with_capacity(self.0.values().map(|sub_sched| sub_sched.len()).sum());
        let mut sub_scheds = self
            .0
            .iter()
            .map(|(info_hash, sub_sched)| {
                assert!(!sub_sched.is_empty());
                (info_hash, sub_sched, 0)
            })
            .collect::<Vec<_>>();
        let mut rng = rand::rng();
        while !sub_scheds.is_empty() {
            let (sub_sched_index, (info_hash, sub_sched, i)) = sub_scheds
                .iter_mut()
                .enumerate()
                .min_by_key(|(_, (info_hash, sub_sched, i))| priority(info_hash, sub_sched, *i))
                .expect("sub_scheds");

            // For now, we do not sort candidates; we merely randomize their order.
            let mut candidates = sub_sched[*i].1.clone();
            candidates.shuffle(&mut rng);

            schedule.push((info_hash.clone(), sub_sched[*i].0, candidates));

            *i += 1;
            if *i >= sub_sched.len() {
                sub_scheds.remove(sub_sched_index);
            }
        }
        schedule
    }
}

impl SubScheduleExt for SubSchedule {
    fn get_candidates_mut(&mut self, index: PieceIndex) -> Option<&mut Candidates> {
        let sub_sched_index = self.iter().position(|(i, _)| i == &index)?;
        Some(&mut self[sub_sched_index].1)
    }
}

impl CandidatesExt for Candidates {
    fn insert_candidate(&mut self, candidate: ConnPair) -> bool {
        if self.contains(&candidate) {
            return false;
        }
        // NOTE: We can use `push` since we are not sorting candidates at the moment.
        self.push(candidate);
        true
    }

    fn remove_candidate(&mut self, candidate: &ConnPair) -> bool {
        let Some(i) = self.iter().position(|cand| cand == candidate) else {
            return false;
        };
        // NOTE: We can use `swap_remove` for the same reason as above.
        self.swap_remove(i);
        true
    }
}
