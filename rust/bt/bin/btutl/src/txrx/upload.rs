use std::io::Error;

use bytes::BytesMut;
use clap::Args;
use futures::sink::SinkExt;
use futures::stream::TryStreamExt;
use tokio::signal;

use bt_base::Bitfield;
use bt_proto::Message;
use bt_proto::tcp::{OwnedSink, OwnedStream};
use bt_storage::Torrent;

use crate::storage::StorageDir;

use super::Txrx;

#[derive(Args, Debug)]
#[command(about = "Upload a torrent to a peer")]
pub(crate) struct UploadCommand {
    #[command(flatten)]
    storage_dir: StorageDir,

    #[command(flatten)]
    txrx: Txrx,
}

impl UploadCommand {
    pub(crate) async fn run(&self) -> Result<(), Error> {
        let (torrent, bitfield) = self.txrx.open(&self.storage_dir.open(false)?)?;
        let num_completed = bitfield.count_ones();
        if num_completed == 0 {
            return Err(Error::other(format!(
                "empty torrent: {}",
                self.txrx.info_hash,
            )));
        }
        let num_pieces = bitfield.len();
        if num_completed < num_pieces {
            tracing::warn!(num_completed, num_pieces, "partial upload");
        }

        let (stream, sink) = self.txrx.handshake(self.txrx.make_stream().await?).await?;

        tokio::select! {
            result = signal::ctrl_c() => {
                result?;
                tracing::info!("ctrl-c received!");
            }
            result = Self::upload(torrent, bitfield, stream, sink) => result?,
        }
        Ok(())
    }

    async fn upload(
        mut torrent: Torrent,
        bitfield: Bitfield,
        mut stream: OwnedStream,
        mut sink: OwnedSink,
    ) -> Result<(), Error> {
        sink.send(Message::bitfield(&bitfield)).await?;

        while let Some(message) = stream.try_next().await? {
            match message {
                Message::Interested => {
                    sink.send(Message::Unchoke).await?;
                }
                Message::NotInterested => {
                    tracing::info!("peer not interested");
                    break;
                }
                Message::Request(range) => {
                    if !bitfield[usize::try_from(range.0.0).expect("usize")] {
                        tracing::warn!(?range, "ignore request for piece that we do not have");
                        continue;
                    }
                    let mut payload = BytesMut::zeroed(usize::try_from(range.2).expect("usize"));
                    torrent.read(range, &mut payload)?;
                    sink.send(Message::Piece(range, payload.freeze())).await?;
                }
                _ => {}
            }
        }

        Ok(())
    }
}
