use std::collections::HashSet;
use std::io::Error;

use clap::Args;
use futures::sink::SinkExt;
use futures::stream::TryStreamExt;
use tokio::signal;

use bt_base::bitfield::BitfieldExt;
use bt_base::{Bitfield, Layout, PieceIndex};
use bt_proto::Message;
use bt_proto::tcp::{OwnedSink, OwnedStream};
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

        let (stream, sink) = self.txrx.handshake(self.txrx.make_stream().await?).await?;

        tokio::select! {
            result = signal::ctrl_c() => {
                result?;
                tracing::info!("ctrl-c received!");
            }
            result = Self::download(torrent, bitfield, layout, stream, sink) => result?,
        }
        Ok(())
    }

    // TODO: This is not very reliable.
    async fn download(
        mut torrent: Torrent,
        bitfield: Bitfield,
        layout: Layout,
        mut stream: OwnedStream,
        mut sink: OwnedSink,
    ) -> Result<(), Error> {
        let mut unchoke = false;
        let mut want_pieces = None;
        while let Some(message) = stream.try_next().await? {
            match message {
                Message::Choke => {
                    tracing::info!("peer choke");
                    return Ok(());
                }
                Message::Unchoke => {
                    unchoke = true;
                }
                Message::Bitfield(payload) => {
                    let mut want =
                        Bitfield::try_from_bytes(&payload, bitfield.len()).map_err(Error::other)?;
                    want &= !bitfield;
                    if want.any() {
                        want_pieces = Some(want);
                        break;
                    } else {
                        tracing::info!("do not want any piece from peer");
                        return Ok(());
                    }
                }
                _ => {}
            }
        }
        let Some(want_pieces) = want_pieces else {
            return Ok(());
        };

        sink.send(Message::Interested).await?;

        if !unchoke {
            while let Some(message) = stream.try_next().await? {
                match message {
                    Message::Choke => {
                        tracing::info!("peer choke");
                        return Ok(());
                    }
                    Message::Unchoke => {
                        break;
                    }
                    _ => {}
                }
            }
        }

        for index in want_pieces.iter_ones() {
            tracing::debug!(index, "download piece");
            let index = PieceIndex(index.try_into().expect("u32"));

            for range in layout.blocks(index, 16384) {
                sink.feed(Message::Request(range)).await?;
            }
            sink.flush().await?;

            let mut ranges = layout.blocks(index, 16384).collect::<HashSet<_>>();
            while let Some(message) = stream.try_next().await? {
                match message {
                    Message::Choke => {
                        tracing::info!("peer choke");
                        return Ok(());
                    }
                    Message::Piece(range, payload) => {
                        if ranges.remove(&range) {
                            torrent.write(range, &payload)?;
                            if ranges.is_empty() {
                                break;
                            }
                        }
                    }
                    _ => {}
                }
            }

            if !torrent.verify(index)? {
                return Err(Error::other(format!("piece verify failed: {index:?}")));
            }
        }

        Ok(())
    }
}
