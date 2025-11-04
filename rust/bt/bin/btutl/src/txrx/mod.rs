mod download;
mod upload;

use std::io::Error;
use std::sync::{Arc, Mutex};

use clap::Args;
use tokio::net::{TcpSocket, TcpStream};

use bt_base::{Features, InfoHash, PeerEndpoint, PeerId};
use bt_model::Model;
use bt_peer::ConnArgs;
use bt_proto::Handshaker;
use bt_proto::tcp;
use bt_storage::Storage;

pub(crate) use self::download::DownloadCommand;
pub(crate) use self::upload::UploadCommand;

#[derive(Args, Debug)]
struct Txrx {
    info_hash: InfoHash,

    #[arg(long, value_name = "ID", help = "Peer id")]
    self_id: Option<PeerId>,
    #[arg(
        long,
        default_value = "0.0.0.0:0",
        value_name = "ENDPOINT",
        help = "Peer endpoint"
    )]
    self_endpoint: PeerEndpoint,

    #[arg(value_name = "ENDPOINT")]
    peer_endpoint: Option<PeerEndpoint>,
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

    async fn make_stream(&self) -> Result<TcpStream, Error> {
        let socket = match self.self_endpoint {
            PeerEndpoint::V4(_) => TcpSocket::new_v4(),
            PeerEndpoint::V6(_) => TcpSocket::new_v6(),
        }?;
        socket.set_reuseport(true)?;
        socket.bind(self.self_endpoint)?;
        tracing::info!(self_endpoint = %socket.local_addr()?);

        match self.peer_endpoint {
            Some(peer_endpoint) => socket.connect(peer_endpoint).await,
            None => socket
                .listen(16)?
                .accept()
                .await
                .map(|(stream, peer_endpoint)| {
                    tracing::info!(%peer_endpoint);
                    stream
                }),
        }
    }

    async fn handshake(&self, mut stream: TcpStream) -> Result<ConnArgs, Error> {
        let self_endpoint = stream.local_addr()?;
        let peer_endpoint = stream.peer_addr()?;

        let self_id = self.self_id.clone().unwrap_or_else(rand::random);
        tracing::info!(%self_id);

        let handshaker = Handshaker::new(self_id, SELF_FEATURES, |info_hash| {
            info_hash == self.info_hash
        });

        let (peer_id, peer_features) = match self.peer_endpoint {
            Some(_) => {
                handshaker
                    .connect(&mut stream, self.info_hash.clone())
                    .await?
            }
            None => {
                let (info_hash, peer_id, peer_features) = handshaker.accept(&mut stream).await?;
                assert_eq!(info_hash, self.info_hash);
                (peer_id, peer_features)
            }
        };
        tracing::info!(%peer_id, ?peer_features);

        let (stream, sink) = tcp::into_split(stream);
        Ok(ConnArgs {
            conn_id: (self.info_hash.clone(), self_endpoint, peer_endpoint).into(),
            self_features: SELF_FEATURES,
            peer_features,
            stream: Box::new(stream),
            sink: Box::new(sink),
        })
    }
}
