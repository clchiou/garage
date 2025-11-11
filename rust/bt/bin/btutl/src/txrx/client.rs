use std::io::Error;
use std::net::Ipv4Addr;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use clap::Args;
use tokio::signal;
use tokio::sync::Mutex as AsyncMutex;
use tokio::time;
use url::Url;

use g1_base::sync::MutexExt;
use g1_tokio::task::{self, Joinable};

use bt_base::{PeerEndpoint, PeerId};
use bt_model::Model;
use bt_net::Net;
use bt_peer::Manifold;
use bt_schedule::Scheduler;
use bt_storage::Storage;
use bt_tracker::{Client, Peers, Request};
use bt_txrx::download::Download;
use bt_txrx::push;
use bt_txrx::upload::Upload;

use crate::storage::StorageDir;

use super::{SELF_FEATURES, Txrx};

#[derive(Args, Debug)]
#[command(about = "Rudimentary BitTorrent client")]
pub(crate) struct ClientCommand {
    #[command(flatten)]
    storage_dir: StorageDir,

    #[command(flatten)]
    txrx: Txrx,

    #[arg(value_name = "ENDPOINT", help = "Self endpoint")]
    self_endpoint: PeerEndpoint,
}

struct Tracker<'a> {
    command: &'a ClientCommand,
    client: Client,
    announce_url: Url,
    self_id: PeerId,
}

impl ClientCommand {
    pub(crate) async fn run(&self) -> Result<(), Error> {
        let self_id = self.txrx.make_self_id();
        let storage = self.storage_dir.open(false)?;
        let model = self.txrx.make_model(&storage)?;
        let tracker = self.make_tracker(self_id.clone(), &storage)?;
        let storage = Arc::new(AsyncMutex::new(storage));

        let (manifold, manifold_guard) = Manifold::spawn(model.clone());
        let (net, net_guard) = super::spawn_net(self_id, model.clone(), manifold.clone());
        let push_guard = push::spawn(SELF_FEATURES, model.clone(), manifold.clone());
        let (download, download_guard) =
            Download::spawn(model.clone(), manifold.clone(), storage.clone());
        let (_, upload_guard) = Upload::spawn(SELF_FEATURES, model.clone(), manifold, storage);
        let (scheduler, scheduler_guard) = Scheduler::spawn(model.clone(), download);

        let mut guard = task::select([
            scheduler_guard.map(Ok).boxed(),
            download_guard,
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
            result = self.client(model.clone(), tracker, scheduler, net) => {
                result?;
            }
            () = &mut guard => {
                tracing::warn!("unexpected actor exit");
            }
        }

        {
            let stat = model
                .must_lock()
                .torrents()
                .get(self.txrx.info_hash.clone())
                .expect("torrent")
                .stat();
            tracing::info!(download = stat.download(), upload = stat.upload());
        }

        guard.shutdown().await?
    }

    fn make_tracker(&self, self_id: PeerId, storage: &Storage) -> Result<Tracker, Error> {
        let metainfo = storage
            .get_metainfo(self.txrx.info_hash.clone())?
            .ok_or_else(|| Error::other("missing metainfo"))?;
        let announce_url = metainfo
            .announce()
            .ok_or_else(|| Error::other("missing announce url"))?;
        let announce_url = announce_url
            .parse()
            .map_err(|_| Error::other(format!("invalid announce url: {announce_url}")))?;
        Ok(Tracker {
            command: self,
            client: Client::new(),
            announce_url,
            self_id,
        })
    }

    async fn client(
        &self,
        model: Arc<Mutex<Model>>,
        tracker: Tracker<'_>,
        scheduler: Scheduler,
        net: Net,
    ) -> Result<(), Error> {
        scheduler.scan().await;

        assert!(net.listen(self.self_endpoint).await?);

        tokio::select! {
            result = async {
                loop {
                    let (interval, peer_endpoints) = tracker.announce().await?;
                    self.insert_peers(&mut model.must_lock(), peer_endpoints);
                    time::sleep(interval).await;
                }
            } => {
                result
            }

            result = self.txrx.wait_completion(model.clone()) => {
                result
            }
        }
    }

    fn insert_peers(&self, model: &mut Model, peer_endpoints: Vec<PeerEndpoint>) {
        let peers_mut = model.peers_mut();
        for peer_endpoint in peer_endpoints {
            peers_mut
                .insert(self.txrx.info_hash.clone(), peer_endpoint)
                .expect("torrent");
        }
    }
}

impl Tracker<'_> {
    async fn announce(&self) -> Result<(Duration, Vec<PeerEndpoint>), Error> {
        let response = self
            .client
            .announce(
                self.announce_url.clone(),
                &Request {
                    info_hash: self.command.txrx.info_hash.clone(),
                    self_id: self.self_id.clone(),
                    port: self.command.self_endpoint.port(),
                    compact: Some(true),
                    ..Default::default()
                },
            )
            .await
            .map_err(Error::other)?;

        let peer_endpoints = match response.peers {
            Peers::PeerEndpoint(peer_endpoints) => peer_endpoints,
            Peers::PeerInfo(peer_infos) => peer_infos
                .into_iter()
                .map(|peer_info| match peer_info.ip.parse::<Ipv4Addr>() {
                    Ok(ip) => Ok((ip, peer_info.port).into()),
                    Err(_) => Err(Error::other(format!("invalid ip: {}", peer_info.ip))),
                })
                .try_collect()?,
        };
        Ok((response.interval, peer_endpoints))
    }
}
