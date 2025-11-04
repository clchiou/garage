use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use g1_base::sync::MutexExt;
use g1_tokio::task::JoinGuard;
use g1_tokio::time::set::naive::FixedDelaySet;

use bt_base::{ConnId, InfoHash};
use bt_model::fold::{self, Closed, Consumer, Fold, FoldGuard};
use bt_model::{ConnState, Model, ModelUpdate, Torrent};
use bt_peer::Manifold;
use bt_proto::Message;

use super::time::FixedDelaySetExt;

struct PushActor {
    model: Arc<Mutex<Model>>,
    changes: Consumer<HashMap<InfoHash, Change>>,

    request_timers: FixedDelaySet<ConnId>,

    manifold: Manifold,
}

pub(super) type PushGuard = JoinGuard<()>;

struct Folder;

// We simply record if `model` has changed; the caller must query `model` to retrieve the current
// value.
#[derive(Default)]
struct Change {
    // TODO: `request_timers` are tied to peers and should be removed when the peers disconnect.
    // The problem is that this process is not synchronous - a peer might reconnect and insert a
    // new entry into `request_timers` before we remove the old ones.  What should we do?
    disconnects: HashSet<ConnId>,

    all: bool,
    some: HashSet<ConnId>,
}

// TODO: Make this parameter configurable.
/// Throttle the sending of `Interested` to a peer.
// I am not sure if this interpretation is correct, but I take a `Interested` message as a request
// for unchoking.
const UNCHOKING_REQUEST_THROTTLE: Duration = Duration::from_secs(32);

pub(super) fn spawn(model: Arc<Mutex<Model>>, manifold: Manifold) -> (PushGuard, FoldGuard) {
    let (changes, fold_guard) = fold::spawn(Folder, model.must_lock().subscribe());
    let actor = PushActor {
        model,
        request_timers: FixedDelaySet::new(UNCHOKING_REQUEST_THROTTLE),
        changes,
        manifold,
    };
    let push_guard = PushGuard::spawn(move |cancel| {
        let mut loop_ = PushActorLoop::new(cancel, actor);
        async move { loop_.run().await }
    });
    (push_guard, fold_guard)
}

fn interested(torrent: &Torrent, conn_id: &ConnId) -> Option<bool> {
    let peer_pieces = torrent.get(&conn_id.conn_pair)?;
    Some(torrent.self_pieces().iter_zeros().any(|i| peer_pieces[i]))
}

#[g1_actor::actor]
impl PushActor {
    #[actor::loop_(react = {
        let changes = self.changes.consume();
        match changes {
            Ok(changes) => self.consume_changes(changes).await,
            Err(Closed) => break,
        }
    })]
    async fn consume_changes(&mut self, changes: HashMap<InfoHash, Change>) {
        let mut interests = HashMap::new();
        let mut requests = Vec::new();
        {
            let model = self.model.must_lock();
            let conn_states = model.conn_states();
            let torrents = model.torrents();
            for (info_hash, change) in changes {
                for conn_id in change.disconnects {
                    self.request_timers.remove_peer(&conn_id);
                }

                let Some(torrent) = torrents.get(info_hash.clone()) else {
                    continue;
                };

                let peers: Box<dyn Iterator<Item = (ConnId, ConnState)>> = if change.all {
                    Box::new(conn_states.conn_states(info_hash))
                } else {
                    Box::new(change.some.into_iter().filter_map(|conn_id| {
                        conn_states
                            .get(&conn_id)
                            .map(|conn_state| (conn_id, conn_state))
                    }))
                };

                for (conn_id, conn_state) in peers {
                    let interest = interested(torrent, &conn_id);

                    let mut already_sent = false;
                    match (conn_state.self_interested(), interest) {
                        (false, Some(true)) => {
                            interests.insert(conn_id.clone(), true);
                            already_sent = true;
                        }
                        (true, Some(false)) => {
                            interests.insert(conn_id.clone(), false);
                        }
                        _ => {}
                    }

                    if conn_state.peer_choking() && interest == Some(true) {
                        requests.push((conn_id, already_sent));
                    } else {
                        self.request_timers.remove_peer(&conn_id);
                    }
                }
            }
        }

        for (conn_id, interest) in interests {
            let message = if interest {
                Message::Interested
            } else {
                Message::NotInterested
            };
            self.manifold.send(&conn_id, message).await;
        }

        for (conn_id, already_sent) in &requests {
            if !*already_sent {
                self.manifold.send(conn_id, Message::Interested).await;
            }
        }
        self.request_timers
            .extend(requests.into_iter().map(|(conn_id, _)| conn_id));
    }

    #[actor::loop_(react = {
        let true = self.request_timers.expired();
        self.request_unchoking().await;
    })]
    async fn request_unchoking(&mut self) {
        let requests = {
            let model = self.model.must_lock();
            let conn_states = model.conn_states();
            let torrents = model.torrents();
            self.request_timers
                .drain_expired()
                .filter_map(|conn_id| {
                    let torrent = torrents.get(conn_id.info_hash())?;
                    let conn_state = conn_states.get(&conn_id)?;
                    (conn_state.peer_choking() && interested(torrent, &conn_id) == Some(true))
                        .then_some(conn_id)
                })
                .collect::<Vec<_>>()
        };
        for conn_id in &requests {
            self.manifold.send(conn_id, Message::Interested).await;
        }
        self.request_timers.extend(requests);
    }
}

impl Fold for Folder {
    type Value = HashMap<InfoHash, Change>;

    fn fold(&mut self, value: &mut Option<Self::Value>, update: ModelUpdate) {
        fn get(value: &mut Option<HashMap<InfoHash, Change>>, info_hash: InfoHash) -> &mut Change {
            value.get_or_insert_default().entry(info_hash).or_default()
        }

        match update {
            ModelUpdate::DisconnectPeer(conn_id) => {
                get(value, conn_id.info_hash()).disconnects.insert(conn_id);
            }

            ModelUpdate::SetSelfPiece(info_hash, _) => {
                get(value, info_hash).all = true;
            }
            ModelUpdate::InitPeer(conn_id)
            | ModelUpdate::SetPeerPiece(conn_id, _)
            | ModelUpdate::PeerChoking(conn_id, _) => {
                get(value, conn_id.info_hash()).some.insert(conn_id);
            }

            // Other updates are irrelevant to us.
            _ => {}
        }
    }
}
