mod download;
mod upload;

use std::io::Error;
use std::sync::{Arc, Mutex};

use clap::Args;

use g1_base::sync::MutexExt;

use bt_base::{Features, InfoHash, PeerEndpoint, PeerId};
use bt_model::Model;
use bt_net::{Net, NetGuard};
use bt_peer::Manifold;
use bt_storage::Storage;

pub(crate) use self::download::DownloadCommand;
pub(crate) use self::upload::UploadCommand;

#[derive(Args, Debug)]
struct Txrx {
    info_hash: InfoHash,

    #[arg(long, value_name = "ID")]
    self_id: Option<PeerId>,
}

#[derive(Args, Debug)]
#[group(required = true)]
struct Endpoints {
    #[arg(long, value_name = "ENDPOINT", help = "Add self endpoint")]
    self_endpoint: Vec<PeerEndpoint>,
    #[arg(long, value_name = "ENDPOINT", help = "Add peer endpoint")]
    peer_endpoint: Vec<PeerEndpoint>,
}

const SELF_FEATURES: Features = Features {
    dht: false,
    fast: false,
    extension: false,
};

impl Txrx {
    fn make_model(&self, storage: &Storage) -> Result<Arc<Mutex<Model>>, Error> {
        let mut torrent = storage
            .open_torrent(self.info_hash.clone())?
            .ok_or_else(|| Error::other(format!("torrent not found: {}", self.info_hash)))?;
        let bitfield = torrent.scan()?;

        let layout = storage
            .get_info(self.info_hash.clone())?
            .expect("info")
            .layout()
            .map_err(Error::other)?;

        let mut model = Model::new();
        assert!(model.new_torrent(self.info_hash.clone()));
        assert!(model.init_torrent(self.info_hash.clone(), layout, bitfield));
        Ok(Arc::new(Mutex::new(model)))
    }

    fn spawn_net(&self, model: Arc<Mutex<Model>>, manifold: Manifold) -> (Net, NetGuard) {
        let self_id = self.self_id.clone().unwrap_or_else(rand::random);
        tracing::info!(%self_id);
        Net::spawn(self_id, SELF_FEATURES, model, manifold, None)
    }
}

impl Endpoints {
    async fn init(
        &self,
        info_hash: InfoHash,
        model: Arc<Mutex<Model>>,
        net: Net,
    ) -> Result<(), Error> {
        for self_endpoint in &self.self_endpoint {
            assert!(net.listen(*self_endpoint).await?);
        }

        if !self.peer_endpoint.is_empty() {
            let mut model = model.must_lock();
            let peers_mut = model.peers_mut();
            for peer_endpoint in &self.peer_endpoint {
                assert_eq!(
                    peers_mut.insert(info_hash.clone(), *peer_endpoint),
                    Ok(true),
                );
            }
        }

        Ok(())
    }
}
