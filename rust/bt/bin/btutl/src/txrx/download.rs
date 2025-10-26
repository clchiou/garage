use std::collections::hash_map::Entry;
use std::collections::{HashMap, HashSet};
use std::io::Error;
use std::sync::{Arc, Mutex};

use clap::Args;
use tokio::signal;

use g1_tokio::task::{Cancel, JoinGuard};

use bt_base::bitfield::{BitfieldExt, BitsliceExt};
use bt_base::{Bitfield, ConnId, Layout};
use bt_model::Model;
use bt_peer::{Conn, Manifold, PeerMessage, PeerMessageRecv};
use bt_proto::Message;
use bt_storage::Torrent;

use crate::storage::StorageDir;

use super::Txrx;

#[derive(Args, Debug)]
#[command(about = "Download a torrent from a peer")]
pub(crate) struct DownloadCommand {
    #[command(flatten)]
    storage_dir: StorageDir,

    #[command(flatten)]
    txrx: Txrx,
}

struct Download {
    bitfield: Bitfield,
    layout: Layout,

    conn_id: ConnId,

    manifold: Manifold,
    peer_message_recv: PeerMessageRecv,

    torrent: Torrent,
}

struct Requester {
    want_pieces: Bitfield,
    layout: Layout,

    conn: Conn,
}

const BLOCK_SIZE: u64 = 16384;

impl DownloadCommand {
    pub(crate) async fn run(&self) -> Result<(), Error> {
        let storage = self.storage_dir.open(false)?;
        let (torrent, bitfield) = self.txrx.open(&storage)?;
        if bitfield.all() {
            tracing::info!("complete torrent");
            return Ok(());
        }

        let layout = storage
            .get_info(self.txrx.info_hash.clone())?
            .expect("info")
            .layout()
            .map_err(Error::other)?;

        let mut model = Model::new();
        assert!(model.new_torrent(self.txrx.info_hash.clone()));
        assert!(model.init_torrent(
            self.txrx.info_hash.clone(),
            layout.clone(),
            bitfield.clone(),
        ));

        let (manifold, mut manifold_guard) = Manifold::spawn(Arc::new(Mutex::new(model)));
        let peer_message_recv = manifold.subscribe();

        let args = self.txrx.handshake(self.txrx.make_stream().await?).await?;
        let conn_id = args.conn_id.clone();
        assert!(manifold.connect(args).await);

        let mut download = Download {
            bitfield,
            layout,

            conn_id,

            manifold,
            peer_message_recv,

            torrent,
        };

        tokio::select! {
            result = signal::ctrl_c() => {
                result?;
                tracing::info!("ctrl-c received!");
            }
            result = download.run() => {
                result?;
            }
            () = &mut manifold_guard => {
                tracing::warn!("unexpected manifold exit");
            }
        }

        Ok(manifold_guard.shutdown().await??)
    }
}

impl Download {
    // TODO: This is not very reliable.
    async fn run(&mut self) -> Result<(), Error> {
        let mut connected = false;
        let mut want_pieces = None;
        let mut requester_guard = None;
        let mut requests = HashMap::new();
        while let Ok(message) = self.peer_message_recv.recv().await {
            if message.conn_id() != &self.conn_id {
                continue;
            }

            match message {
                PeerMessage::Connect(_) => {
                    assert!(!connected);
                    connected = true;
                    self.manifold
                        .send(&self.conn_id, Message::bitfield(&self.bitfield))
                        .await;
                }

                PeerMessage::Disconnect(_, result) => {
                    assert!(connected);
                    match result {
                        Ok(()) => tracing::warn!("unexpected disconnect"),
                        Err(error) => tracing::warn!(%error, "conn"),
                    }
                    break;
                }

                PeerMessage::Message(_, message) => match message {
                    Message::Bitfield(payload) => {
                        assert!(want_pieces.is_none());

                        let mut want = Bitfield::try_from_bytes(&payload, self.bitfield.len())
                            .map_err(Error::other)?;
                        want &= !self.bitfield.clone();
                        if want.not_any() {
                            tracing::info!("do not want any piece from peer");
                            break;
                        }
                        want_pieces = Some(want);

                        self.manifold.send(&self.conn_id, Message::Interested).await;
                    }

                    Message::Choke => {
                        tracing::info!("peer choke");
                        break;
                    }

                    Message::Unchoke => {
                        if requester_guard.is_some() {
                            continue;
                        }

                        let want_pieces = want_pieces.take().expect("want_pieces");

                        requests.extend(want_pieces.iter_haves().map(|index| {
                            (
                                index,
                                self.layout
                                    .blocks(index, BLOCK_SIZE)
                                    .collect::<HashSet<_>>(),
                            )
                        }));

                        let Some(conn) = self.manifold.get(&self.conn_id) else {
                            tracing::warn!("unexpected conn exit");
                            break;
                        };
                        let actor = Requester {
                            want_pieces,
                            layout: self.layout.clone(),
                            conn,
                        };
                        requester_guard = Some(JoinGuard::spawn(move |cancel| actor.run(cancel)));
                    }

                    Message::Piece(range, payload) => {
                        let index = range.0;
                        let Entry::Occupied(mut entry) = requests.entry(index) else {
                            tracing::warn!(?range, "unexpected block");
                            continue;
                        };
                        if !entry.get_mut().remove(&range) {
                            tracing::warn!(?range, "unexpected block");
                            continue;
                        }

                        self.torrent.write(range, &payload)?;

                        if !entry.get().is_empty() {
                            continue;
                        }
                        entry.remove();

                        if !self.torrent.verify(index)? {
                            return Err(Error::other(format!("piece verify failed: {index:?}")));
                        }

                        if requests.is_empty() {
                            tracing::info!("all pieces downloaded");
                            break;
                        }
                    }

                    _ => {}
                },
            }
        }
        if let Some(mut requester_guard) = requester_guard {
            requester_guard.shutdown().await?;
        }
        Ok(())
    }
}

impl Requester {
    async fn run(self, cancel: Cancel) {
        tokio::select! {
            () = cancel.wait() => {}
            () = self.request() => {}
        }
    }

    async fn request(&self) {
        for index in self.want_pieces.iter_haves() {
            tracing::debug!(?index, "request");
            for range in self.layout.blocks(index, BLOCK_SIZE) {
                self.conn.send(Message::Request(range)).await;
            }
        }
    }
}
