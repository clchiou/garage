use std::collections::HashSet;
use std::io::Error;
use std::sync::{Arc, Mutex};

use bytes::BytesMut;
use tokio::sync::Mutex as AsyncMutex;

use g1_base::sync::MutexExt;
use g1_tokio::task::{self, BoxJoinable, Joinable};

use bt_base::{BlockRange, ConnId, Features, InfoHash};
use bt_model::fold::{self, Closed, Consumer, Fold};
use bt_model::{ConnState, Model, ModelUpdate, PeerStat};
use bt_peer::{Manifold, PeerMessage, PeerMessageRecv};
use bt_proto::Message;
use bt_storage::Storage;

struct UploadActor {
    self_features: Features,

    model: Arc<Mutex<Model>>,
    removes: Consumer<HashSet<InfoHash>>,

    paused: HashSet<InfoHash>,
    seeding: HashSet<InfoHash>,

    manifold: Manifold,
    peer_message_recv: PeerMessageRecv,

    storage: Arc<AsyncMutex<Storage>>,
}

pub type UploadGuard = BoxJoinable<Result<(), Error>>;

struct Folder;

//
// TODO: Make these parameters configurable.
//

/// Maximum size of a peer's requested blocks.
const REQUEST_SIZE_LIMIT: u64 = 64 * 1024;

/// Threshold of data at which we will choke the peer.
const RECIPROCATE_UPPER: u64 = RECIPROCATE_LOWER + 128 * 1024;
/// Threshold of data at which we will unchoke the peer.
const RECIPROCATE_LOWER: u64 = 128 * 1024;

impl Upload {
    pub fn spawn(
        self_features: Features,
        model: Arc<Mutex<Model>>,
        manifold: Manifold,
        // TODO: Require a mutex because it is not currently designed for concurrent access.
        storage: Arc<AsyncMutex<Storage>>,
    ) -> (Self, UploadGuard) {
        let (removes, fold_guard) = fold::spawn(Folder, model.must_lock().subscribe());

        let peer_message_recv = manifold.subscribe();
        let (this, upload_guard) = Self::spawn_impl(UploadActor {
            self_features,

            model,
            removes,

            paused: HashSet::new(),
            seeding: HashSet::new(),

            manifold,
            peer_message_recv,

            storage,
        });

        (
            this,
            task::select([upload_guard.boxed(), fold_guard.map(Ok).boxed()]).boxed(),
        )
    }
}

impl Fold for Folder {
    type Value = HashSet<InfoHash>;

    fn fold(&mut self, value: &mut Option<Self::Value>, update: ModelUpdate) {
        if let ModelUpdate::RemoveTorrent(info_hash) = update {
            value.get_or_insert_default().insert(info_hash);
        }
    }
}

#[g1_actor::actor(
    stub(
        pub, Upload,
        spawn(spawn_impl),
    ),
    loop_(
        type Result<(), Error>,
        return Ok(()),
    ),
)]
impl UploadActor {
    #[actor::method(pub, stub(return { let result: () = (); }))]
    async fn pause(&mut self, info_hash: InfoHash) {
        self.paused.insert(info_hash);
    }

    #[actor::method(pub, stub(return { let result: () = (); }))]
    async fn resume(&mut self, info_hash: InfoHash) {
        self.paused.remove(&info_hash);
    }

    #[actor::method(pub, stub(return { let result: () = (); }))]
    async fn seed(&mut self, info_hash: InfoHash) {
        self.seeding.insert(info_hash);
    }

    #[actor::method(pub, stub(return { let result: () = (); }))]
    async fn unseed(&mut self, info_hash: InfoHash) {
        self.seeding.remove(&info_hash);
    }

    #[actor::loop_(react = {
        let removes = self.removes.consume();
        match removes {
            Ok(removes) => self.consume_removes(removes).await,
            Err(Closed) => break,
        }
    })]
    async fn consume_removes(&mut self, removes: HashSet<InfoHash>) {
        for info_hash in removes {
            self.paused.remove(&info_hash);
            self.seeding.remove(&info_hash);
        }
    }

    #[actor::loop_(react = {
        let message = self.peer_message_recv.recv();
        match message {
            Ok(message) => self.recv_peer_message(message).await?,
            Err(_) => break,
        }
    })]
    async fn recv_peer_message(&self, message: PeerMessage) -> Result<(), Error> {
        let PeerMessage::Message(conn_id, message) = message else {
            return Ok(());
        };

        if self.seeding.contains(&conn_id.info_hash) {
            self.seed_block(&conn_id, message).await
        } else {
            self.upload_block(&conn_id, message).await
        }
    }

    async fn upload_block(&self, conn_id: &ConnId, message: Message) -> Result<(), Error> {
        match message {
            // I am not sure if this interpretation is correct, but I take a `Interested` message
            // as a request for unchoking.
            Message::Interested => {
                let change = request_unchoking(&self.model.must_lock(), conn_id);

                if let Some(Some(message)) = change {
                    self.manifold.send(conn_id, message).await;
                }
            }

            // TODO: Since `Storage` is non-concurrent, there is not much value in uploading
            // concurrently at the moment.
            Message::Request(range) => {
                if !self.check_request_size(conn_id, range).await {
                    return Ok(());
                }

                let Some((choke, reject, peer_features_fast)) =
                    request_block(&self.model.must_lock(), conn_id, range)
                else {
                    return Ok(());
                };

                if choke {
                    self.manifold.send(conn_id, Message::Choke).await;
                }
                if choke || reject || self.paused.contains(&conn_id.info_hash) {
                    if self.self_features.fast && peer_features_fast {
                        self.manifold.send(conn_id, Message::Reject(range)).await;
                    }
                    return Ok(());
                }

                self.send_block(conn_id, range).await?;
            }

            _ => {}
        }
        Ok(())
    }

    async fn seed_block(&self, conn_id: &ConnId, message: Message) -> Result<(), Error> {
        //
        // Disregard snubbing during seeding.
        //
        match message {
            Message::Interested => {
                let self_choking = self
                    .model
                    .must_lock()
                    .conn_states()
                    .get(conn_id)
                    .map(|conn_state| conn_state.self_choking());

                if self_choking == Some(true) {
                    self.manifold.send(conn_id, Message::Unchoke).await;
                }
            }

            Message::Request(range) => {
                if !self.check_request_size(conn_id, range).await {
                    return Ok(());
                }

                let (reject, peer_features_fast) = {
                    let model = self.model.must_lock();
                    let Some(conn_state) = model.conn_states().get(conn_id) else {
                        return Ok(());
                    };
                    let Some(torrent) = model.torrents().get(conn_id.info_hash()) else {
                        return Ok(());
                    };
                    (
                        conn_state.self_choking() || !torrent.self_pieces()[range.index()],
                        conn_state.peer_features().fast,
                    )
                };

                if reject || self.paused.contains(&conn_id.info_hash) {
                    if self.self_features.fast && peer_features_fast {
                        self.manifold.send(conn_id, Message::Reject(range)).await;
                    }
                    return Ok(());
                }

                self.send_block(conn_id, range).await?;
            }

            _ => {}
        }
        Ok(())
    }

    async fn check_request_size(&self, conn_id: &ConnId, range: BlockRange) -> bool {
        if range.2 <= REQUEST_SIZE_LIMIT {
            return true;
        }

        tracing::warn!(%conn_id, ?range, "request size limit exceeded");
        let peer_features_fast = self
            .model
            .must_lock()
            .conn_states()
            .get(conn_id)
            .is_some_and(|conn_state| conn_state.peer_features().fast);
        if self.self_features.fast && peer_features_fast {
            self.manifold.send(conn_id, Message::Reject(range)).await;
        }
        false
    }

    async fn send_block(&self, conn_id: &ConnId, range: BlockRange) -> Result<(), Error> {
        let mut payload = BytesMut::zeroed(range.size());
        {
            let storage = self.storage.lock().await;
            let Some(mut torrent) = storage.open_torrent(conn_id.info_hash())? else {
                return Ok(());
            };
            torrent.read(range, &mut payload)?;
        }
        self.manifold
            .send(conn_id, Message::Piece(range, payload.freeze()))
            .await;
        Ok(())
    }
}

// At the moment, we are implementing a very simple reciprocation scheme.
fn next_conn_state(
    conn_state: &ConnState,
    peer_stat: &PeerStat,
    request_size: u64,
) -> Option<Message> {
    let freeride = (peer_stat.send_sum() + request_size).saturating_sub(peer_stat.recv_sum());
    if conn_state.self_choking() {
        (freeride < RECIPROCATE_LOWER).then_some(Message::Unchoke)
    } else {
        // We treat snubbing as a form of choking and will use this opportunity to make our
        // intentions explicit.
        (conn_state.snubbing() || freeride >= RECIPROCATE_UPPER).then_some(Message::Choke)
    }
}

fn request_unchoking(model: &Model, conn_id: &ConnId) -> Option<Option<Message>> {
    let conn_state = model.conn_states().get(conn_id)?;
    let peer_stat = model
        .torrents()
        .get(conn_id.info_hash())?
        .peer_stats()
        .get(&conn_id.conn_pair)?;
    Some(next_conn_state(&conn_state, &peer_stat, 0))
}

fn request_block(model: &Model, conn_id: &ConnId, range: BlockRange) -> Option<(bool, bool, bool)> {
    let conn_state = model.conn_states().get(conn_id)?;
    let torrent = model.torrents().get(conn_id.info_hash())?;
    let peer_stat = torrent.peer_stats().get(&conn_id.conn_pair)?;
    Some((
        next_conn_state(&conn_state, &peer_stat, range.2) == Some(Message::Choke),
        conn_state.self_choking() || conn_state.snubbing() || !torrent.self_pieces()[range.index()],
        conn_state.peer_features().fast,
    ))
}
