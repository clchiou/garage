use std::collections::{HashMap, HashSet};
use std::ops::ControlFlow;
use std::sync::{Arc, Mutex};

use g1_base::sync::MutexExt;
use g1_tokio::task::{self, BoxJoinable, JoinGuard, Joinable};

use bt_base::{ConnId, Features, InfoHash, PieceIndex};
use bt_model::fold::{self, Closed, Consumer, Fold};
use bt_model::{Model, ModelUpdate};
use bt_peer::Manifold;
use bt_proto::Message;

struct PushActor {
    self_features: Features,

    model: Arc<Mutex<Model>>,
    changes: Consumer<HashMap<InfoHash, Change>>,

    manifold: Manifold,
}

pub type PushGuard = BoxJoinable<()>;

struct Folder;

// We simply record if `model` has changed; the caller must query `model` to retrieve the current
// value.
//
// NOTE: What should we do when a torrent has been removed and then reinitialized?  `connects`
// should be handled the same way, since we should send a `Bitfield` regardless of torrent
// reinitialization.  But what about `haves`?  Our end goal is to synchronize the peer's bitfield
// with ours.  In theory, we should generate a diff between the old and new bitfields and send that
// diff to every peer - but this is too complicated, and the protocol does not support sending a
// full diff anyway.  Given that connections will be disconnected when the torrent is removed,
// perhaps the best approach is simply to handle `haves` as if the torrent were never
// reinitialized.
#[derive(Default)]
struct Change {
    connects: HashSet<ConnId>,
    haves: HashSet<PieceIndex>,
}

pub fn spawn(self_features: Features, model: Arc<Mutex<Model>>, manifold: Manifold) -> PushGuard {
    let (changes, fold_guard) = fold::spawn(Folder, model.must_lock().subscribe());
    let actor = PushActor {
        self_features,
        model,
        changes,
        manifold,
    };
    let push_guard = JoinGuard::spawn(move |cancel| {
        let mut loop_ = PushActorLoop::new(cancel, actor);
        async move { loop_.run().await }
    });
    task::try_fold([push_guard, fold_guard], (), |acc, result| {
        assert!(matches!(acc, Ok(())));
        ControlFlow::Break(result)
    })
    .boxed()
}

// `Bitfield` and `Interested` are sent in separate `PushActor`s, which means they may be sent out
// of order, though this is probably not a major concern.
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
        let mut bitfields = HashMap::new();
        let mut haves = Vec::new();
        {
            let model = self.model.must_lock();
            let conn_states = model.conn_states();
            let torrents = model.torrents();
            for (info_hash, mut change) in changes {
                let Some(torrent) = torrents.get(info_hash.clone()) else {
                    continue;
                };

                let self_pieces = torrent.self_pieces();

                let bitfield = Message::bitfield(self_pieces);
                let have_all = self_pieces.all();
                let have_none = self_pieces.not_any();
                for conn_id in change.connects {
                    let Some(conn_state) = conn_states.get(&conn_id) else {
                        continue;
                    };
                    let fast = self.self_features.fast && conn_state.peer_features().fast;
                    let message = if fast && have_all {
                        Message::HaveAll
                    } else if fast && have_none {
                        Message::HaveNone
                    } else {
                        bitfield.clone()
                    };
                    bitfields.insert(conn_id, message);
                }

                change
                    .haves
                    .retain(|index| self_pieces[usize::from(*index)]);
                if !change.haves.is_empty() {
                    haves.push((
                        conn_states
                            .conn_states(info_hash.clone())
                            .filter_map(|(conn_id, _)| {
                                // If we are sending `Bitfield`, there is no need to send `Have`.
                                (!bitfields.contains_key(&conn_id)).then_some(conn_id)
                            })
                            .collect::<Vec<_>>(),
                        change.haves,
                    ));
                }
            }
        }

        for (conn_id, message) in bitfields {
            self.manifold.send(&conn_id, message).await;
        }

        for (conn_ids, haves) in haves {
            for conn_id in conn_ids {
                for index in &haves {
                    self.manifold.send(&conn_id, Message::Have(*index)).await;
                }
            }
        }
    }
}

impl Fold for Folder {
    type Value = HashMap<InfoHash, Change>;

    fn fold(&mut self, value: &mut Option<Self::Value>, update: ModelUpdate) {
        fn get(value: &mut Option<HashMap<InfoHash, Change>>, info_hash: InfoHash) -> &mut Change {
            value.get_or_insert_default().entry(info_hash).or_default()
        }

        match update {
            ModelUpdate::ConnectPeer(conn_id) => {
                get(value, conn_id.info_hash()).connects.insert(conn_id);
            }
            ModelUpdate::SetSelfPiece(info_hash, index) => {
                get(value, info_hash).haves.insert(index);
            }
            // Other updates are irrelevant to us.
            _ => {}
        }
    }
}
