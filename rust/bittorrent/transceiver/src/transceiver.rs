use std::io::Error;
use std::sync::Arc;

use bytes::Bytes;
use tokio::sync::broadcast::{self, Receiver, Sender};

use g1_tokio::task::JoinGuard;

use bittorrent_base::Dimension;
use bittorrent_dht::Dht;
use bittorrent_manager::Manager;
use bittorrent_peer::Recvs;

use crate::{
    actor::{Actor, DynStorage, Update},
    bitfield::{Bitfield, BitfieldExt},
    stat::{Torrent, TorrentInner},
};

#[derive(Clone, Debug)]
pub struct Transceiver {
    pub torrent: Torrent,
    // Only for subscribing.
    update_send: Sender<Update>,
}

pub type TransceiverGuard = JoinGuard<Result<(), Error>>;

pub type TransceiverSpawn = impl FnOnce() -> (Transceiver, TransceiverGuard);

impl Transceiver {
    #[define_opaque(TransceiverSpawn)]
    pub async fn prepare_spawn(
        raw_info: Bytes,
        dim: Dimension,
        manager: Manager,
        recvs: Recvs,
        mut storage: DynStorage,
        dht_ipv4: Option<Dht>,
        dht_ipv6: Option<Dht>,
    ) -> Result<(TransceiverSpawn, Torrent, Receiver<Update>), Error> {
        let self_pieces = storage.scan().await?;
        Bitfield::from_bytes(self_pieces.as_raw_slice(), dim.num_pieces)
            .ok_or_else(|| Error::other("expect no spare bits in self_pieces"))?;

        let torrent_inner = Arc::new(TorrentInner::new(
            self_pieces
                .iter_ones()
                .map(|piece| dim.piece_size(piece.into()))
                .sum(),
            dim.size,
        ));
        let torrent = Torrent::new(torrent_inner.clone());

        let (update_send, update_recv) = broadcast::channel(*crate::update_queue_size());

        let spawn = {
            let torrent = torrent.clone();
            move || {
                (
                    Transceiver {
                        torrent,
                        update_send: update_send.clone(),
                    },
                    JoinGuard::spawn(move |cancel| {
                        Actor::new(
                            cancel,
                            raw_info,
                            dim,
                            self_pieces,
                            manager,
                            recvs,
                            storage,
                            dht_ipv4,
                            dht_ipv6,
                            torrent_inner,
                            update_send,
                        )
                        .run()
                    }),
                )
            }
        };

        Ok((spawn, torrent, update_recv))
    }

    pub fn subscribe(&self) -> Receiver<Update> {
        self.update_send.subscribe()
    }
}
