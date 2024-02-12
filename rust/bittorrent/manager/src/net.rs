use std::io::{Error, ErrorKind};
use std::sync::Arc;
use std::time::Duration;

use tokio::{
    net::{TcpListener, TcpSocket},
    time,
};

use g1_tokio::{io::DynStream, net::tcp::TcpStream};

use bittorrent_base::{Features, InfoHash, PeerId};
use bittorrent_mse::MseStream;
use bittorrent_utp::{UtpSocket, UtpStream};

use crate::{error, Cipher, Endpoint, Preference, Socket, Transport, CIPHERS, TRANSPORTS};

fn fill_prefs(mut prefs: Vec<Preference>) -> Vec<Preference> {
    for transport in TRANSPORTS {
        for cipher in CIPHERS {
            let pref = (*transport, *cipher);
            if !prefs.contains(&pref) {
                prefs.push(pref);
            }
        }
    }
    prefs
}

#[derive(Debug)]
pub(crate) struct Connector {
    info_hash: InfoHash,
    self_id: PeerId,
    self_features: Features,
    peer_id: Option<PeerId>,
    peer_endpoint: Endpoint,

    prefs: Vec<Preference>,

    connect_timeout: Duration,
    utp_socket_v4: Option<Arc<UtpSocket>>,
    utp_socket_v6: Option<Arc<UtpSocket>>,
}

#[derive(Debug)]
pub(crate) struct Acceptor {
    info_hash: InfoHash,
    self_id: PeerId,
    self_features: Features,

    tcp_listener_v4: Option<TcpListener>,
    tcp_listener_v6: Option<TcpListener>,
    utp_socket_v4: Option<Arc<UtpSocket>>,
    utp_socket_v6: Option<Arc<UtpSocket>>,
}

impl Connector {
    const DEFAULT_PREFS: &'static [Preference] = &[
        (Transport::Tcp, Cipher::Mse),
        (Transport::Utp, Cipher::Mse),
        (Transport::Tcp, Cipher::Plaintext),
        (Transport::Utp, Cipher::Plaintext),
    ];

    pub(crate) fn new_default(
        info_hash: InfoHash,
        peer_id: Option<PeerId>,
        peer_endpoint: Endpoint,
        prefs: Option<Vec<Preference>>,
        utp_socket_v4: Option<Arc<UtpSocket>>,
        utp_socket_v6: Option<Arc<UtpSocket>>,
    ) -> Self {
        Self::new(
            info_hash,
            bittorrent_base::self_id().clone(),
            Features::load(),
            peer_id,
            peer_endpoint,
            prefs.unwrap_or_else(|| Vec::from(Self::DEFAULT_PREFS)),
            *crate::connect_timeout(),
            utp_socket_v4,
            utp_socket_v6,
        )
    }

    #[allow(clippy::too_many_arguments)]
    pub(crate) fn new(
        info_hash: InfoHash,
        self_id: PeerId,
        self_features: Features,
        peer_id: Option<PeerId>,
        peer_endpoint: Endpoint,
        prefs: Vec<Preference>,
        connect_timeout: Duration,
        utp_socket_v4: Option<Arc<UtpSocket>>,
        utp_socket_v6: Option<Arc<UtpSocket>>,
    ) -> Self {
        Self {
            info_hash,
            self_id,
            self_features,
            peer_id,
            peer_endpoint,
            prefs: fill_prefs(prefs),
            connect_timeout,
            utp_socket_v4,
            utp_socket_v6,
        }
    }

    pub(crate) fn set_peer_id(&mut self, peer_id: Option<PeerId>) {
        self.peer_id = peer_id;
    }

    pub(crate) fn set_preferences(&mut self, prefs: Vec<Preference>) {
        self.prefs = fill_prefs(prefs);
    }

    pub(crate) async fn connect(&mut self) -> Result<Socket, Error> {
        for (i, pref) in self.prefs.iter().copied().enumerate() {
            match self.connect_by_pref(pref).await {
                Ok(socket) => {
                    let (transport, cipher) = pref;
                    tracing::debug!(
                        ?transport,
                        ?cipher,
                        peer_endpoint = ?self.peer_endpoint,
                        "connect",
                    );
                    if i != 0 {
                        let pref = self.prefs.remove(i);
                        self.prefs.insert(0, pref);
                    }
                    return Ok(socket);
                }
                Err(error) => {
                    if error.kind() == ErrorKind::TimedOut {
                        tracing::debug!(
                            peer_endpoint = ?self.peer_endpoint,
                            ?error,
                            "peer connect timeout",
                        );
                    } else {
                        tracing::warn!(
                            peer_endpoint = ?self.peer_endpoint,
                            ?error,
                            "peer connect error",
                        );
                    }
                }
            }
        }
        Err(error::Error::ConnectError.into())
    }

    async fn connect_by_pref(&self, (transport, cipher): Preference) -> Result<Socket, Error> {
        let stream = time::timeout(self.connect_timeout, async {
            match transport {
                Transport::Tcp => self.tcp_connect().await,
                Transport::Utp => self.utp_connect().await,
            }
        })
        .await
        .map_err(|_| error::Error::ConnectTimeout { transport })??;

        let stream = match cipher {
            Cipher::Mse => bittorrent_mse::connect(stream, self.info_hash.as_ref())
                .await?
                .into(),
            Cipher::Plaintext => stream,
        };

        Socket::connect(
            stream,
            self.info_hash.clone(),
            self.self_id.clone(),
            self.self_features,
            self.peer_id.clone(),
        )
        .await
    }

    async fn tcp_connect(&self) -> Result<DynStream<'static>, Error> {
        let socket = if self.peer_endpoint.is_ipv4() {
            TcpSocket::new_v4()
        } else {
            assert!(self.peer_endpoint.is_ipv6());
            TcpSocket::new_v6()
        }?;
        socket.set_reuseaddr(true)?;
        Ok(Box::new(TcpStream::from(
            socket.connect(self.peer_endpoint).await?,
        )))
    }

    async fn utp_connect(&self) -> Result<DynStream<'static>, Error> {
        let socket = if self.peer_endpoint.is_ipv4() {
            self.utp_socket_v4.as_ref()
        } else {
            assert!(self.peer_endpoint.is_ipv6());
            self.utp_socket_v6.as_ref()
        }
        .ok_or(error::Error::UtpNotEnabled)?;
        Ok(Box::new(socket.connect(self.peer_endpoint).await?))
    }
}

impl Acceptor {
    pub(crate) fn new_default(
        info_hash: InfoHash,
        tcp_listener_v4: Option<TcpListener>,
        tcp_listener_v6: Option<TcpListener>,
        utp_socket_v4: Option<Arc<UtpSocket>>,
        utp_socket_v6: Option<Arc<UtpSocket>>,
    ) -> Self {
        Self::new(
            info_hash,
            bittorrent_base::self_id().clone(),
            Features::load(),
            tcp_listener_v4,
            tcp_listener_v6,
            utp_socket_v4,
            utp_socket_v6,
        )
    }

    pub(crate) fn new(
        info_hash: InfoHash,
        self_id: PeerId,
        self_features: Features,
        tcp_listener_v4: Option<TcpListener>,
        tcp_listener_v6: Option<TcpListener>,
        utp_socket_v4: Option<Arc<UtpSocket>>,
        utp_socket_v6: Option<Arc<UtpSocket>>,
    ) -> Self {
        assert!(
            tcp_listener_v4.is_some()
                || tcp_listener_v6.is_some()
                || utp_socket_v4.is_some()
                || utp_socket_v6.is_some()
        );
        Self {
            info_hash,
            self_id,
            self_features,
            tcp_listener_v4,
            tcp_listener_v6,
            utp_socket_v4,
            utp_socket_v6,
        }
    }

    pub(crate) async fn accept(&self) -> Result<(Socket, Endpoint, Vec<Preference>), Error> {
        let (stream, peer_endpoint, prefs) = tokio::select! {
            Some(stream) = async {
                match self.tcp_listener_v4.as_ref() {
                    Some(tcp_listener) => Some(tcp_listener.accept().await),
                    None => None,
                }
            } => {
                let (stream, peer_endpoint) = stream?;
                let (stream, prefs) = self.tcp_accept(stream.into()).await?;
                (stream, peer_endpoint, prefs)
            }

            Some(stream) = async {
                match self.tcp_listener_v6.as_ref() {
                    Some(tcp_listener) => Some(tcp_listener.accept().await),
                    None => None,
                }
            } => {
                let (stream, peer_endpoint) = stream?;
                let (stream, prefs) = self.tcp_accept(stream.into()).await?;
                (stream, peer_endpoint, prefs)
            }

            Some(stream) = async {
                match self.utp_socket_v4.as_ref() {
                    Some(utp_socket) => Some(utp_socket.accept().await),
                    None => None,
                }
            } => {
                let stream = stream?;
                let peer_endpoint = stream.peer_endpoint();
                let (stream, prefs) = self.utp_accept(stream).await?;
                (stream, peer_endpoint, prefs)
            }

            Some(stream) = async {
                match self.utp_socket_v6.as_ref() {
                    Some(utp_socket) => Some(utp_socket.accept().await),
                    None => None,
                }
            } => {
                let stream = stream?;
                let peer_endpoint = stream.peer_endpoint();
                let (stream, prefs) = self.utp_accept(stream).await?;
                (stream, peer_endpoint, prefs)
            }
        };

        let socket = Socket::accept(
            stream,
            self.info_hash.clone(),
            self.self_id.clone(),
            self.self_features,
            // TODO: Should we look up the peer id if we have connected to this peer before?
            None,
        )
        .await?;

        tracing::debug!(transport = ?prefs[0].0, cipher = ?prefs[0].1, ?peer_endpoint, "accept");
        Ok((socket, peer_endpoint, prefs))
    }

    async fn tcp_accept(
        &self,
        stream: TcpStream,
    ) -> Result<(DynStream<'static>, Vec<Preference>), Error> {
        let stream = bittorrent_mse::accept(stream, self.info_hash.as_ref()).await?;
        let prefs = Self::new_prefs(&[Transport::Tcp, Transport::Utp], &stream);
        Ok((stream.into(), prefs))
    }

    async fn utp_accept(
        &self,
        stream: UtpStream,
    ) -> Result<(DynStream<'static>, Vec<Preference>), Error> {
        let stream = bittorrent_mse::accept(stream, self.info_hash.as_ref()).await?;
        let prefs = Self::new_prefs(&[Transport::Utp, Transport::Tcp], &stream);
        Ok((stream.into(), prefs))
    }

    fn new_prefs<Stream>(transports: &[Transport], stream: &MseStream<Stream>) -> Vec<Preference> {
        let ciphers = match stream {
            MseStream::Rc4(_) => &[Cipher::Mse, Cipher::Plaintext],
            MseStream::Plaintext(_) => &[Cipher::Plaintext, Cipher::Mse],
        };

        let mut prefs = Vec::new();
        for transport in transports {
            for cipher in ciphers {
                prefs.push((*transport, *cipher));
            }
        }
        fill_prefs(prefs)
    }
}
