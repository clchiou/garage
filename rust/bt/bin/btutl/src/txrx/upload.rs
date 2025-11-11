use std::io::Error;
use std::sync::{Arc, Mutex};

use clap::Args;
use tokio::signal;
use tokio::sync::Mutex as AsyncMutex;

use g1_base::sync::MutexExt;
use g1_tokio::task::{self, Joinable};

use bt_model::Model;
use bt_net::Net;
use bt_peer::Manifold;
use bt_txrx::push;
use bt_txrx::upload::Upload;

use crate::storage::StorageDir;

use super::{Endpoints, SELF_FEATURES, Txrx};

#[derive(Args, Debug)]
#[command(about = "Upload a torrent to peers")]
pub(crate) struct UploadCommand {
    #[command(flatten)]
    storage_dir: StorageDir,

    #[command(flatten)]
    txrx: Txrx,

    #[command(flatten)]
    endpoints: Endpoints,

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
        let self_id = self.txrx.make_self_id();

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

        let (net, net_guard) = super::spawn_net(self_id, model.clone(), manifold.clone());

        let push_guard = push::spawn(SELF_FEATURES, model.clone(), manifold.clone());

        let (upload, upload_guard) = Upload::spawn(
            SELF_FEATURES,
            model.clone(),
            manifold,
            Arc::new(AsyncMutex::new(storage)),
        );

        let mut guard = task::select([
            upload_guard,
            push_guard.map(Ok).boxed(),
            manifold_guard
                .map(|result| result.map_err(Error::from))
                .boxed(),
            net_guard.boxed(),
        ]);

        tokio::select! {
            result = signal::ctrl_c() => {
                result?;
                tracing::info!("ctrl-c received!");
            }
            Err(error) = self.upload(model, upload, net) => {
                return Err(error);
            }
            () = &mut guard => {
                tracing::warn!("unexpected actor exit");
            }
        }
        guard.shutdown().await?
    }

    async fn upload(
        &self,
        model: Arc<Mutex<Model>>,
        upload: Upload,
        net: Net,
    ) -> Result<(), Error> {
        if self.seed == Some(true) {
            upload.seed(self.txrx.info_hash.clone()).await;
        }
        self.endpoints
            .init(self.txrx.info_hash.clone(), model, net)
            .await
    }
}
