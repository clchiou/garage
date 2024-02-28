#[macro_use]
mod macros {
    macro_rules! ensure_block {
        ($self:ident, $peer:ident, $block:ident $(,)?) => {{
            let Some(block) = $self.dim.check_block_desc($block) else {
                tracing::warn!(
                    peer_endpoint = ?$peer.peer_endpoint(),
                    ?$block,
                    "close peer due to invalid block",
                );
                $peer.cancel();
                return Ok(());
            };
            block
        }};
    }
}

mod dht;
mod download;
mod extension;
mod peer;
mod run;
mod upload;

use std::sync::Arc;

use bytes::Bytes;
use tokio::sync::{
    broadcast::{Receiver, Sender},
    oneshot::error::RecvError,
};

use bittorrent_base::{BlockDesc, Dimension, Features, PieceIndex};
use bittorrent_dht::Dht;
use bittorrent_manager::{Endpoint, Manager, Update as PeerUpdate};
use bittorrent_peer::Recvs;
use bittorrent_storage::{Bitfield, Storage};

use g1_base::{
    fmt::{DebugExt, InsertPlaceholder},
    future::ReadyQueue,
};
use g1_tokio::task::Cancel;

use crate::{
    queue::Queues,
    schedule::Scheduler,
    stat::{Stats, TorrentInner},
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Update {
    Start,
    Download(PieceIndex),
    Idle,
    Complete,
    Stop,
}

pub type DynStorage = Box<dyn Storage + Send + 'static>;

#[derive(DebugExt)]
pub(crate) struct Actor {
    cancel: Cancel,

    raw_info: Bytes,
    dim: Dimension,
    self_features: Features,
    self_pieces: Bitfield,

    // For now, we do not evict any `stats` entries.
    stats: Stats,
    reciprocate_margin: u64,

    scheduler: Scheduler,
    endgame: bool,
    endgame_threshold: f64,
    endgame_max_assignments: usize,
    endgame_max_replicates: usize,

    queues: Queues,
    #[debug(with = InsertPlaceholder)]
    responses: ReadyQueue<(Endpoint, BlockDesc, Result<Bytes, RecvError>)>,

    manager: Manager,

    peer_update_recv: Receiver<(Endpoint, PeerUpdate)>,
    recvs: Recvs,

    #[debug(with = InsertPlaceholder)]
    storage: DynStorage,

    dht_ipv4: Option<Dht>,
    dht_ipv6: Option<Dht>,

    torrent: Arc<TorrentInner>,
    update_send: Sender<Update>,
}

impl Actor {
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn new(
        cancel: Cancel,

        raw_info: Bytes,
        dim: Dimension,
        self_pieces: Bitfield,

        manager: Manager,
        recvs: Recvs,
        storage: DynStorage,
        dht_ipv4: Option<Dht>,
        dht_ipv6: Option<Dht>,

        torrent: Arc<TorrentInner>,
        update_send: Sender<Update>,
    ) -> Self {
        let scheduler = Scheduler::new(dim.clone(), &self_pieces);
        let queues = Queues::new(dim.clone());
        let peer_update_recv = manager.subscribe();
        Self {
            cancel,

            raw_info,
            dim,
            self_features: Features::load(),
            self_pieces,

            stats: Stats::new(),
            reciprocate_margin: *crate::reciprocate_margin(),

            scheduler,
            endgame: false,
            endgame_threshold: *crate::endgame_threshold(),
            endgame_max_assignments: *crate::endgame_max_assignments(),
            endgame_max_replicates: *crate::endgame_max_replicates(),

            queues,
            responses: ReadyQueue::new(),

            manager,

            peer_update_recv,
            recvs,

            storage,

            dht_ipv4,
            dht_ipv6,

            torrent,
            update_send,
        }
    }
}
