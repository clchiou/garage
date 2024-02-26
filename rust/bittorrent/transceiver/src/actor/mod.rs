#[macro_use]
mod macros {
    macro_rules! try_then {
        ($value:expr, $then:expr $(,)?) => {
            match $value {
                Some(value) => value,
                None => $then,
            }
        };
    }

    macro_rules! ensure_block {
        ($self:ident, $peer:ident, $block:ident $(,)?) => {
            try_then!($self.dim.check_block_desc($block), {
                tracing::warn!(
                    peer_endpoint = ?$peer.peer_endpoint(),
                    ?$block,
                    "close peer due to invalid block",
                );
                $peer.cancel();
                return Ok(());
            })
        };
    }
}

mod dht;
mod download;
mod extension;
mod peer;
mod run;
mod upload;

use std::io::Error;
use std::sync::Arc;

use bytes::Bytes;
use tokio::sync::{
    broadcast::{Receiver, Sender},
    oneshot::error::RecvError,
    Notify,
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
    exit: Arc<Notify>,

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

    pub(crate) torrent: Arc<TorrentInner>,
    update_send: Sender<Update>,
}

impl Actor {
    #[allow(clippy::too_many_arguments)]
    pub(crate) async fn make(
        exit: Arc<Notify>,
        raw_info: Bytes,
        dim: Dimension,
        manager: Manager,
        recvs: Recvs,
        mut storage: DynStorage,
        dht_ipv4: Option<Dht>,
        dht_ipv6: Option<Dht>,
        update_send: Sender<Update>,
    ) -> Result<Self, Error> {
        let self_pieces = storage.scan().await?;
        use crate::bitfield::{Bitfield, BitfieldExt};
        Bitfield::from_bytes(self_pieces.as_raw_slice(), dim.num_pieces)
            .ok_or_else(|| Error::other("expect no spare bits in self_pieces"))?;

        let scheduler = Scheduler::new(dim.clone(), &self_pieces);
        let queues = Queues::new(dim.clone());
        let peer_update_recv = manager.subscribe();
        let torrent = Arc::new(TorrentInner::new(
            self_pieces
                .iter_ones()
                .map(|piece| dim.piece_size(piece.into()))
                .sum(),
            dim.size,
        ));

        Ok(Self {
            exit,

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
        })
    }
}
