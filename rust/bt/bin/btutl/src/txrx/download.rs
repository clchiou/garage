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
use bt_schedule::Scheduler;
use bt_txrx::download::Download;
use bt_txrx::push;

use crate::storage::StorageDir;

use super::{Endpoints, SELF_FEATURES, Txrx};

#[derive(Args, Debug)]
#[command(about = "Download a torrent from peers")]
pub(crate) struct DownloadCommand {
    #[command(flatten)]
    storage_dir: StorageDir,

    #[command(flatten)]
    txrx: Txrx,

    #[command(flatten)]
    endpoints: Endpoints,
}

impl DownloadCommand {
    pub(crate) async fn run(&self) -> Result<(), Error> {
        let self_id = self.txrx.make_self_id();

        let storage = self.storage_dir.open(false)?;

        let model = self.txrx.make_model(&storage)?;
        {
            let model = model.must_lock();
            if model
                .torrents()
                .get(self.txrx.info_hash.clone())
                .expect("torrent")
                .self_pieces()
                .all()
            {
                tracing::info!("complete torrent");
                return Ok(());
            }
        }

        let (manifold, manifold_guard) = Manifold::spawn(model.clone());

        let (net, net_guard) = super::spawn_net(self_id, model.clone(), manifold.clone());

        let push_guard = push::spawn(SELF_FEATURES, model.clone(), manifold.clone());

        let (download, download_guard) =
            Download::spawn(model.clone(), manifold, Arc::new(AsyncMutex::new(storage)));

        let (scheduler, scheduler_guard) = Scheduler::spawn(model.clone(), download);

        let mut guard = task::select([
            scheduler_guard.map(Ok).boxed(),
            download_guard,
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
            result = self.download(model, scheduler, net) => {
                result?;
            }
            () = &mut guard => {
                tracing::warn!("unexpected manifold exit");
            }
        }
        guard.shutdown().await?
    }

    async fn download(
        &self,
        model: Arc<Mutex<Model>>,
        scheduler: Scheduler,
        net: Net,
    ) -> Result<(), Error> {
        scheduler.scan().await;

        self.endpoints
            .init(self.txrx.info_hash.clone(), model.clone(), net)
            .await?;

        self.txrx.wait_completion(model).await
    }
}
