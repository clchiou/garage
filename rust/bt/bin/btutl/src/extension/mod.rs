mod metadata;

use std::io::{Error, ErrorKind};
use std::sync::{Arc, Mutex};

use bytes::Bytes;
use clap::Args;
use tokio::io::AsyncWriteExt;
use tokio::net::TcpSocket;

use g1_tokio::task::joinable::select::Select;
use g1_tokio::task::{self, JoinGuard};

use bt_base::{ConnId, Features, InfoHash, PeerEndpoint, PeerId};
use bt_model::Model;
use bt_peer::half_open::{HalfOpenConn, HalfOpenManifold, HalfOpenMessage, HalfOpenMessageRecv};
use bt_peer::{self, ConnArgs, Manifold};
use bt_proto::Handshaker;
use bt_proto::tcp;

pub(crate) use self::metadata::DownloadMetadataCommand;

#[derive(Args, Debug)]
struct Extension {
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
    peer_endpoint: PeerEndpoint,
}

#[derive(Debug)]
struct ExtensionConn {
    conn_id: ConnId,
    state: Option<bool>,
    recv: HalfOpenMessageRecv,
    send: HalfOpenConn,
}

type ExtensionGuard = Select<JoinGuard<Result<(), bt_peer::Error>>, 2, bt_peer::Error>;

impl Extension {
    async fn spawn(&self) -> Result<(ExtensionConn, ExtensionGuard), Error> {
        let model = Arc::new(Mutex::new(Model::new()));
        let (manifold, manifold_guard) = Manifold::spawn(model.clone());
        let (half_open, half_open_guard) = HalfOpenManifold::spawn(model, manifold);

        let recv = half_open.subscribe();

        let args = self.connect().await?;
        let conn_id = args.conn_id.clone();
        assert!(half_open.connect(args).await);
        let send = half_open
            .get(&conn_id)
            .ok_or_else(|| Error::other("unexpected conn exit"))?;

        Ok((
            ExtensionConn {
                conn_id,
                state: None,
                recv,
                send,
            },
            task::select([manifold_guard, half_open_guard]),
        ))
    }

    async fn connect(&self) -> Result<ConnArgs, Error> {
        let socket = match self.self_endpoint {
            PeerEndpoint::V4(_) => TcpSocket::new_v4(),
            PeerEndpoint::V6(_) => TcpSocket::new_v6(),
        }?;
        socket.set_reuseport(true)?;
        socket.bind(self.self_endpoint)?;

        let mut stream = socket.connect(self.peer_endpoint).await?;

        let self_endpoint = stream.local_addr()?;
        tracing::info!(%self_endpoint);
        let peer_endpoint = stream.peer_addr()?;

        let self_id = self.self_id.clone().unwrap_or_else(rand::random);
        tracing::info!(%self_id);

        let self_features = Features {
            dht: false,
            fast: false,
            extension: true,
        };

        let (peer_id, peer_features) = Handshaker::new(self_id, self_features, ())
            .connect(&mut stream, self.info_hash.clone())
            .await?;
        tracing::info!(%peer_id, ?peer_features);

        if !peer_features.extension {
            stream.shutdown().await?;
            return Err(Error::other("peer does not support extension"));
        }

        let (stream, sink) = tcp::into_split(stream);
        Ok(ConnArgs {
            conn_id: (self.info_hash.clone(), self_endpoint, peer_endpoint).into(),
            self_features,
            peer_features,
            stream: Box::new(stream),
            sink: Box::new(sink),
        })
    }
}

impl ExtensionConn {
    async fn recv(&mut self) -> Result<(u8, Bytes), Error> {
        loop {
            let message =
                self.recv.recv().await.map_err(|_| {
                    Error::new(ErrorKind::UnexpectedEof, "unexpected manifold exit")
                })?;
            assert_eq!(message.conn_id(), &self.conn_id);
            match message {
                HalfOpenMessage::Connect(_) => {
                    assert_eq!(self.state, None);
                    self.state = Some(true);
                }
                HalfOpenMessage::Extended(_, id, payload) => {
                    assert_eq!(self.state, Some(true));
                    return Ok((id, payload));
                }
                HalfOpenMessage::Disconnect(_, _) => {
                    assert_eq!(self.state, Some(true));
                    self.state = Some(false);
                    return Err(Error::new(ErrorKind::UnexpectedEof, "peer disconnect"));
                }
            }
        }
    }

    async fn send(&self, id: u8, payload: Bytes) {
        self.send.send(id, payload).await
    }
}
