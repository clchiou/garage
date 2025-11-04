mod push;
mod schedule;
mod state;
mod time;

use std::collections::HashSet;
use std::io::Error;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use bytes::Bytes;
use tokio::sync::Mutex as AsyncMutex;
use tokio::sync::broadcast::{self, Receiver, Sender, WeakSender};

use g1_base::sync::MutexExt;
use g1_tokio::task::{self, BoxJoinable, Joinable};
use g1_tokio::time::set::naive::FixedDelaySet;

use bt_base::{BlockRange, ConnId, InfoHash};
use bt_model::fold::{self, Closed, Consumer, Fold};
use bt_model::{Model, ModelUpdate};
use bt_peer::{Manifold, PeerMessage, PeerMessageRecv};
use bt_proto::Message;
use bt_storage::Storage;

use self::schedule::ScheduleExt;
use self::state::DownloadState;
use self::time::FixedDelaySetExt;

struct DownloadActor {
    model: Arc<Mutex<Model>>,
    change: Consumer<Change>,

    schedule: Schedule,
    download: DownloadState,

    request_timeouts: FixedDelaySet<(ConnId, BlockRange)>,
    snub_watchdogs: FixedDelaySet<ConnId>,

    manifold: Manifold,
    peer_message_recv: PeerMessageRecv,

    storage: Arc<AsyncMutex<Storage>>,

    sender: Sender<DownloadUpdate>,
}

pub type DownloadGuard = BoxJoinable<Result<(), Error>>;

pub use self::schedule::Schedule;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DownloadUpdate {
    ScheduleLen(usize),
}

pub type DownloadUpdateRecv = Receiver<DownloadUpdate>;

struct Folder;

// We simply record if `model` has changed; the caller must query `model` to retrieve the current
// value.
#[derive(Default)]
struct Change {
    chokes: HashSet<ConnId>,

    // TODO: Our states are tied to torrents and should be removed when the torrents are removed.
    // The problem is that this process is not synchronous - a torrent might be reinitialized, and
    // the caller could insert new states before we remove the old ones.  What should we do?
    removes: HashSet<InfoHash>,
}

//
// TODO: Make these parameters configurable.
//

/// Timeout for our requests.
const REQUEST_TIMEOUT: Duration = Duration::from_secs(8);

/// Duration of inactivity after which we snub a peer.
const SNUB_TIMEOUT: Duration = Duration::from_secs(32);

impl Download {
    pub fn spawn(
        model: Arc<Mutex<Model>>,
        manifold: Manifold,
        // TODO: Require a mutex because it is not currently designed for concurrent access.
        storage: Arc<AsyncMutex<Storage>>,
    ) -> (Self, DownloadGuard) {
        let (change, fold_guard) = fold::spawn(Folder, model.must_lock().subscribe());

        // TODO: Make channel capacity configurable.
        let (sender, _) = broadcast::channel(32);
        let subscriber = sender.downgrade();

        let actor = DownloadActor {
            model: model.clone(),
            change,

            schedule: Schedule::new(),
            download: DownloadState::new(),

            request_timeouts: FixedDelaySet::new(REQUEST_TIMEOUT),
            snub_watchdogs: FixedDelaySet::new(SNUB_TIMEOUT),

            manifold: manifold.clone(),
            peer_message_recv: manifold.subscribe(),

            storage,

            sender,
        };
        let (this, download_guard) = Self::spawn_impl(subscriber, actor);

        let (push_guard_0, push_guard_1) = push::spawn(model, manifold);

        (
            this,
            task::select([
                download_guard.boxed(),
                fold_guard.map(Ok).boxed(),
                push_guard_0.map(Ok).boxed(),
                push_guard_1.map(Ok).boxed(),
            ])
            .boxed(),
        )
    }

    pub fn subscribe(&self) -> Option<DownloadUpdateRecv> {
        self.subscriber
            .upgrade()
            .map(|subscriber| subscriber.subscribe())
    }
}

impl Fold for Folder {
    type Value = Change;

    fn fold(&mut self, value: &mut Option<Self::Value>, update: ModelUpdate) {
        match update {
            ModelUpdate::PeerChoking(conn_id, _) | ModelUpdate::Snubbing(conn_id, _) => {
                value.get_or_insert_default().chokes.insert(conn_id);
            }

            ModelUpdate::RemoveTorrent(info_hash) => {
                value.get_or_insert_default().removes.insert(info_hash);
            }

            // Other updates are irrelevant to us.
            _ => {}
        }
    }
}

#[g1_actor::actor(
    stub(
        pub, Download, struct {
            subscriber: WeakSender<DownloadUpdate>,
        },
        spawn(spawn_impl),
    ),
    loop_(
        type Result<(), Error>,
        return Ok(()),
    ),
)]
impl DownloadActor {
    #[actor::method(pub, stub(return { let result: () = (); }))]
    async fn assign(&mut self, schedule: Schedule) {
        tracing::debug!(schedule_len = schedule.len(), "assign");
        // For now, for the sake of simplicity, we overwrite the current `schedule` rather than
        // calculating the difference.
        self.schedule = schedule;
        self.broadcast_schedule_len();

        // We do not remove existing assignments.
        self.assign_then_send_requests().await;
    }

    #[actor::method(pub, stub(return { let result: Option<usize> = result.ok(); }))]
    fn schedule_len(&self) -> usize {
        self.schedule.len()
    }

    fn broadcast_schedule_len(&self) {
        let _ = self
            .sender
            .send(DownloadUpdate::ScheduleLen(self.schedule.len()));
    }

    #[actor::method(pub, stub(return { let result: () = (); }))]
    async fn pause(&mut self, info_hash: InfoHash) {
        if self.download.pause(info_hash.clone()) {
            tracing::info!(%info_hash, "pause");
            self.assign_then_send_requests().await;
        }
    }

    #[actor::method(pub, stub(return { let result: () = (); }))]
    async fn resume(&mut self, info_hash: InfoHash) {
        if self.download.resume(info_hash.clone()) {
            tracing::info!(%info_hash, "resume");
            self.assign_then_send_requests().await;
        }
    }

    #[actor::loop_(react = {
        let change = self.change.consume();
        match change {
            Ok(change) => self.consume_change(change).await,
            Err(Closed) => break,
        }
    })]
    async fn consume_change(&mut self, change: Change) {
        let len = self.schedule.len();
        for info_hash in change.removes {
            self.schedule.remove_torrent(info_hash.clone());
            self.download.remove_torrent(info_hash.clone());
            self.request_timeouts.remove_torrent(info_hash.clone());
            self.snub_watchdogs.remove_torrent(info_hash);
        }
        if len != self.schedule.len() {
            self.broadcast_schedule_len();
        }

        {
            let model = self.model.must_lock();
            let conn_states = model.conn_states();
            for conn_id in change.chokes {
                if conn_states
                    .get(&conn_id)
                    .is_some_and(|conn_state| conn_state.peer_choking() || conn_state.snubbing())
                {
                    self.download.remove_peer(&conn_id);
                    self.request_timeouts.remove_peer(&conn_id);
                    self.snub_watchdogs.remove_peer(&conn_id);
                }
            }
        }

        self.assign_then_send_requests().await;
    }

    #[actor::loop_(react = {
        let message = self.peer_message_recv.recv();
        match message {
            Ok(message) => self.recv_peer_message(message).await?,
            Err(_) => break,
        }
    })]
    async fn recv_peer_message(&mut self, message: PeerMessage) -> Result<(), Error> {
        match message {
            PeerMessage::Connect { .. } => {}

            PeerMessage::Disconnect(conn_id, _) => {
                //
                // Keep `schedule` entries, as we usually reconnect to this peer afterward.
                //

                let removed = self.download.remove_peer(&conn_id);
                self.request_timeouts.remove_peer(&conn_id);
                self.snub_watchdogs.remove_peer(&conn_id);

                if removed {
                    self.assign_then_send_requests().await;
                }
            }

            PeerMessage::Message(conn_id, message) => match message {
                Message::Piece(range, block) => self.recv_block(&conn_id, range, block).await?,
                Message::Reject(range) => self.reject(&conn_id, range).await,
                _ => {}
            },
        }
        Ok(())
    }

    async fn assign_then_send_requests(&mut self) {
        let assigned = self
            .download
            .assign(&self.model.must_lock(), &self.schedule);

        for conn_id in assigned {
            self.send_requests(&conn_id).await;
        }
    }

    // NOTE: The caller must ensure that `conn_id` exists in `self.download.window`.
    async fn send_requests(&mut self, conn_id: &ConnId) {
        let pending = self.download.queue_requests(conn_id).expect("requests");

        for range in pending {
            self.manifold.send(conn_id, Message::Request(range)).await;

            assert!(self.request_timeouts.insert_new((conn_id.clone(), range)));
            self.snub_watchdogs.insert_new(conn_id.clone());
        }
    }

    async fn recv_block(
        &mut self,
        conn_id: &ConnId,
        range: BlockRange,
        block: Bytes,
    ) -> Result<(), Error> {
        self.request_timeouts.remove(&(conn_id.clone(), range));

        // We un-snub the peer and reset the watchdog regardless of whether the request entry is
        // present in `download`, since we might have already removed the entry.
        if let Some(conn_state) = self.model.must_lock().conn_states().get(conn_id) {
            conn_state.set_snubbing(false);
        }
        self.snub_watchdogs.update(conn_id);

        let Some((last, cancels)) = self.download.recv(conn_id, range) else {
            tracing::debug!(%conn_id, ?range, "drop incoming block");
            return Ok(());
        };

        let index = range.0;
        if last {
            self.download.remove_piece(conn_id.info_hash(), index);
        }

        for conn_id in cancels {
            self.manifold.send(&conn_id, Message::Cancel(range)).await;
        }

        let verify = {
            let storage = self.storage.lock().await;
            let Some(mut torrent) = storage.open_torrent(conn_id.info_hash())? else {
                return Ok(());
            };

            torrent.write(range, &block)?;

            if last {
                Some(torrent.verify(index)?)
            } else {
                None
            }
        };

        let info_hash = &conn_id.info_hash;
        match verify {
            Some(true) => {
                tracing::info!(%info_hash, ?index, "piece verify");

                if let Some(torrent) = self
                    .model
                    .must_lock()
                    .torrents_mut()
                    .get_mut(conn_id.info_hash())
                {
                    torrent.set_self_piece(index);
                }

                let len = self.schedule.len();
                self.schedule.remove_piece(conn_id.info_hash(), index);
                if len != self.schedule.len() {
                    self.broadcast_schedule_len();
                }
            }
            Some(false) => {
                tracing::warn!(%info_hash, ?index, "piece verify failed");
            }
            None => {}
        }

        if last {
            self.assign_then_send_requests().await;
            // We should not snub a peer just because we are not assigning pieces to them.
            if !self.download.is_assigned(conn_id) {
                self.snub_watchdogs.remove(conn_id);
            }
        } else {
            self.send_requests(conn_id).await;
        }

        Ok(())
    }

    async fn reject(&mut self, conn_id: &ConnId, range: BlockRange) {
        self.request_timeouts.remove(&(conn_id.clone(), range));
        if self.download.reject(conn_id, range) {
            tracing::debug!(%conn_id, ?range, "request rejected");
            self.send_requests(conn_id).await;
        }
    }

    #[actor::loop_(react = {
        let true = self.request_timeouts.expired();
        self.request_timeout().await;
    })]
    async fn request_timeout(&mut self) {
        let timeouts = self.request_timeouts.drain_expired().collect::<Vec<_>>();
        for (conn_id, range) in timeouts {
            if self.download.reject(&conn_id, range) {
                tracing::debug!(%conn_id, ?range, "request timeout");
                self.send_requests(&conn_id).await;
            }
        }
    }

    // TODO: How do we un-snub peers?  We could opportunistically send block requests to those we
    // have snubbed, or simply un-snub them after a timeout.
    #[actor::loop_(react = {
        let true = self.snub_watchdogs.expired();
        self.snub_peers();
    })]
    fn snub_peers(&mut self) {
        let model = self.model.must_lock();
        let conn_states = model.conn_states();
        for conn_id in self.snub_watchdogs.drain_expired() {
            if let Some(conn_state) = conn_states.get(&conn_id) {
                tracing::warn!(%conn_id, "snub");
                conn_state.set_snubbing(true);
            }
        }
    }
}
