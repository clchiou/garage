use std::io::Error;
use std::sync::Arc;

use clap::Args;
use tokio::signal;
use tokio::sync::Mutex as AsyncMutex;

use g1_base::sync::MutexExt;
use g1_tokio::task::{self, Joinable};

use bt_peer::{Manifold, PeerMessage};
use bt_txrx::push;
use bt_txrx::upload::Upload;

use crate::storage::StorageDir;

use super::{SELF_FEATURES, Txrx};

#[derive(Args, Debug)]
#[command(about = "Upload a torrent to a peer")]
pub(crate) struct UploadCommand {
    #[command(flatten)]
    storage_dir: StorageDir,

    #[command(flatten)]
    txrx: Txrx,

    #[arg(
        long,
        value_name = "BOOL",
        default_value = "true",
        help = "Seed the torrent"
    )]
    seed: Option<bool>,
}

impl UploadCommand {
    pub(crate) async fn run(&self) -> Result<(), Error> {
        let storage = self.storage_dir.open(false)?;

        let model = self.txrx.make_model(&storage)?;
        {
            let model = model.must_lock();
            let self_pieces = model
                .torrents()
                .get(self.txrx.info_hash.clone())
                .expect("torrent")
                .self_pieces();
            let num_completed = self_pieces.count_ones();
            if num_completed == 0 {
                return Err(Error::other(format!(
                    "empty torrent: {}",
                    self.txrx.info_hash,
                )));
            }
            let num_pieces = self_pieces.len();
            if num_completed < num_pieces {
                tracing::warn!(num_completed, num_pieces, "partial upload");
            }
        }

        let (manifold, manifold_guard) = Manifold::spawn(model.clone());

        let push_guard = push::spawn(SELF_FEATURES, model.clone(), manifold.clone());

        let (upload, upload_guard) = Upload::spawn(
            SELF_FEATURES,
            model,
            manifold.clone(),
            Arc::new(AsyncMutex::new(storage)),
        );

        let mut guard = task::select([
            upload_guard,
            push_guard.map(Ok).boxed(),
            manifold_guard
                .map(|result| result.map_err(Error::from))
                .boxed(),
        ]);

        tokio::select! {
            result = signal::ctrl_c() => {
                result?;
                tracing::info!("ctrl-c received!");
            }
            result = self.upload(upload, manifold) => {
                result?;
            }
            () = &mut guard => {
                tracing::warn!("unexpected actor exit");
            }
        }
        guard.shutdown().await?
    }

    async fn upload(&self, upload: Upload, manifold: Manifold) -> Result<(), Error> {
        if self.seed == Some(true) {
            upload.seed(self.txrx.info_hash.clone()).await;
        }

        let mut peer_message_recv = manifold.subscribe();

        let args = self.txrx.handshake(self.txrx.make_stream().await?).await?;
        let conn_id = args.conn_id.clone();
        assert!(manifold.connect(args).await);

        while let Ok(message) = peer_message_recv.recv().await {
            if matches!(message, PeerMessage::Disconnect(id, _) if id == conn_id) {
                return Ok(());
            }
        }
        Err(Error::other("unexpected manifold exit"))
    }
}
