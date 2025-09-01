mod download;
mod upload;

use std::io::Error;

use clap::Args;
use tokio::net::{TcpSocket, TcpStream};

use bt_base::{Bitfield, Features, InfoHash, PeerEndpoint, PeerId};
use bt_proto::Handshaker;
use bt_proto::tcp::{self, OwnedSink, OwnedStream};
use bt_storage::{Storage, Torrent};

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

impl Txrx {
    fn open(&self, storage: &Storage) -> Result<(Torrent, Bitfield), Error> {
        let mut torrent = storage
            .open_torrent(self.info_hash.clone())?
            .ok_or_else(|| Error::other(format!("torrent not found: {}", self.info_hash)))?;
        let bitfield = torrent.scan()?;
        Ok((torrent, bitfield))
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

    async fn handshake(&self, mut stream: TcpStream) -> Result<(OwnedStream, OwnedSink), Error> {
        let self_id = self.self_id.clone().unwrap_or_else(rand::random);
        tracing::info!(%self_id);

        let handshaker = Handshaker::new(
            self_id,
            Features {
                dht: false,
                fast: false,
                extension: false,
            },
            |info_hash| info_hash == self.info_hash,
        );

        let (peer_id, peer_features) = match self.peer_endpoint {
            Some(_) => {
                handshaker
                    .connect(&mut stream, self.info_hash.clone())
                    .await
            }
            None => handshaker.accept(&mut stream).await,
        }?;
        tracing::info!(%peer_id, ?peer_features);

        Ok(tcp::into_split(stream))
    }
}
