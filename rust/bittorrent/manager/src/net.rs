use std::future::Future;
use std::io::{Error, ErrorKind};
use std::time::Duration;

use futures::future::{BoxFuture, FutureExt, OptionFuture};
use tokio::{
    net::{TcpListener, TcpSocket},
    time,
};
use tracing::{field, Instrument, Span};

use g1_tokio::{
    bstream::{StreamRecv, StreamSend},
    io::DynStream,
    net::tcp::TcpStream,
};

use bittorrent_base::{Features, InfoHash, PeerId};
use bittorrent_mse::MseStream;
use bittorrent_utp::{UtpConnector, UtpListener};

use crate::{error, Cipher, Endpoint, Preference, Socket, Transport};

type Prefs = [Preference; 4];

#[derive(Debug)]
pub(crate) struct Connector {
    info_hash: InfoHash,
    self_id: PeerId,
    self_features: Features,
    peer_id: Option<PeerId>,
    peer_endpoint: Endpoint,

    prefs: Prefs,

    connect_timeout: Duration,
    utp_connector_ipv4: Option<UtpConnector>,
    utp_connector_ipv6: Option<UtpConnector>,
}

#[derive(Debug)]
pub(crate) struct Listener {
    info_hash: InfoHash,
    self_id: PeerId,
    self_features: Features,

    tcp_listener_ipv4: Option<TcpListener>,
    tcp_listener_ipv6: Option<TcpListener>,
    utp_listener_ipv4: Option<UtpListener>,
    utp_listener_ipv6: Option<UtpListener>,
}

impl Connector {
    const DEFAULT_PREFS: Prefs = [
        (Transport::Tcp, Cipher::Mse),
        (Transport::Utp, Cipher::Mse),
        (Transport::Tcp, Cipher::Plaintext),
        (Transport::Utp, Cipher::Plaintext),
    ];

    pub(crate) fn new(
        info_hash: InfoHash,
        peer_endpoint: Endpoint,
        utp_connector_ipv4: Option<UtpConnector>,
        utp_connector_ipv6: Option<UtpConnector>,
    ) -> Self {
        Self::with_param(
            info_hash,
            bittorrent_base::self_id().clone(),
            Features::load(),
            peer_endpoint,
            *crate::connect_timeout(),
            utp_connector_ipv4,
            utp_connector_ipv6,
        )
    }

    pub(crate) fn with_param(
        info_hash: InfoHash,
        self_id: PeerId,
        self_features: Features,
        peer_endpoint: Endpoint,
        connect_timeout: Duration,
        utp_connector_ipv4: Option<UtpConnector>,
        utp_connector_ipv6: Option<UtpConnector>,
    ) -> Self {
        Self {
            info_hash,
            self_id,
            self_features,
            peer_id: None,
            peer_endpoint,
            prefs: Self::DEFAULT_PREFS,
            connect_timeout,
            utp_connector_ipv4,
            utp_connector_ipv6,
        }
    }

    pub(crate) fn set_peer_id(&mut self, peer_id: Option<PeerId>) {
        self.peer_id = peer_id;
    }

    pub(crate) async fn connect(&mut self) -> Result<Socket, Error> {
        for (i, (transport, cipher)) in self.prefs.iter().copied().enumerate() {
            let result = self
                .try_connect(transport, cipher)
                .inspect(|result| {
                    match result {
                        Ok(socket) => {
                            let peer_id = socket.peer_id();
                            tracing::debug!(?peer_id);
                            if let Some(expect) = self.peer_id.as_ref() {
                                if &peer_id != expect {
                                    // TODO: Should we close the connection as specified in BEP 3?
                                    tracing::warn!(?peer_id, ?expect, "unexpected peer_id");
                                }
                            }
                        }
                        Err(error) => match error.kind() {
                            ErrorKind::TimedOut => {
                                tracing::debug!(?error, "peer connect timeout");
                            }
                            ErrorKind::ConnectionRefused => {
                                tracing::debug!(?error, "peer connect refused");
                            }
                            _ => {
                                tracing::warn!(?error, "peer connect error");
                            }
                        },
                    }
                })
                .instrument(tracing::info_span!(
                    "mgr/connect",
                    ?transport,
                    ?cipher,
                    peer_endpoint = ?self.peer_endpoint,
                ))
                .await;
            if result.is_ok() {
                self.prefs[0..=i].rotate_right(1);
                return result;
            }
        }
        Err(error::Error::Unreachable {
            peer_endpoint: self.peer_endpoint,
        }
        .into())
    }

    async fn try_connect(&self, transport: Transport, cipher: Cipher) -> Result<Socket, Error> {
        let stream = time::timeout(self.connect_timeout, async {
            match transport {
                Transport::Tcp => self.tcp_connect().await,
                Transport::Utp => self.utp_connect().await,
            }
        })
        .await
        .map_err(|_| error::Error::ConnectTimeout {
            peer_endpoint: self.peer_endpoint,
            transport,
        })??;

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
        let connector = if self.peer_endpoint.is_ipv4() {
            self.utp_connector_ipv4.as_ref()
        } else {
            assert!(self.peer_endpoint.is_ipv6());
            self.utp_connector_ipv6.as_ref()
        }
        .ok_or(error::Error::UtpNotEnabled {
            peer_endpoint: self.peer_endpoint,
        })?;
        Ok(Box::new(connector.connect(self.peer_endpoint).await?))
    }
}

impl Listener {
    pub(crate) fn new(
        info_hash: InfoHash,
        tcp_listener_ipv4: Option<TcpListener>,
        tcp_listener_ipv6: Option<TcpListener>,
        utp_listener_ipv4: Option<UtpListener>,
        utp_listener_ipv6: Option<UtpListener>,
    ) -> Self {
        Self::with_param(
            info_hash,
            bittorrent_base::self_id().clone(),
            Features::load(),
            tcp_listener_ipv4,
            tcp_listener_ipv6,
            utp_listener_ipv4,
            utp_listener_ipv6,
        )
    }

    pub(crate) fn with_param(
        info_hash: InfoHash,
        self_id: PeerId,
        self_features: Features,
        tcp_listener_ipv4: Option<TcpListener>,
        tcp_listener_ipv6: Option<TcpListener>,
        utp_listener_ipv4: Option<UtpListener>,
        utp_listener_ipv6: Option<UtpListener>,
    ) -> Self {
        assert!(
            tcp_listener_ipv4.is_some()
                || tcp_listener_ipv6.is_some()
                || utp_listener_ipv4.is_some()
                || utp_listener_ipv6.is_some()
        );
        Self {
            info_hash,
            self_id,
            self_features,
            tcp_listener_ipv4,
            tcp_listener_ipv6,
            utp_listener_ipv4,
            utp_listener_ipv6,
        }
    }

    pub(crate) async fn accept(
        &self,
    ) -> Result<
        (
            Endpoint,
            Option<Endpoint>,
            impl Future<Output = Result<Socket, Error>> + Send + 'static,
        ),
        Error,
    > {
        macro_rules! accept {
            ($listener:ident $(,)?) => {
                OptionFuture::from(self.$listener.as_ref().map(|listener| listener.accept()))
            };
        }

        macro_rules! tcp_handshake {
            ($stream:ident $(,)?) => {{
                let (stream, peer_endpoint) = $stream?;
                (
                    Transport::Tcp,
                    peer_endpoint,
                    Box::pin(Self::handshake(
                        self.info_hash.clone(),
                        self.self_id.clone(),
                        self.self_features,
                        TcpStream::from(stream),
                    )),
                )
            }};
        }

        macro_rules! utp_handshake {
            ($stream:ident $(,)?) => {{
                let stream = $stream?;
                (
                    Transport::Utp,
                    stream.peer_endpoint(),
                    Box::pin(Self::handshake(
                        self.info_hash.clone(),
                        self.self_id.clone(),
                        self.self_features,
                        stream,
                    )),
                )
            }};
        }

        let (transport, peer_endpoint, handshake): (
            _,
            _,
            BoxFuture<'static, Result<Socket, Error>>,
        ) = tokio::select! {
            Some(stream) = accept!(tcp_listener_ipv4) => tcp_handshake!(stream),
            Some(stream) = accept!(tcp_listener_ipv6) => tcp_handshake!(stream),
            Some(stream) = accept!(utp_listener_ipv4) => utp_handshake!(stream),
            Some(stream) = accept!(utp_listener_ipv6) => utp_handshake!(stream),
        };

        // TODO: I assume that the peer's uTP connecting endpoint is also the peer's uTP and TCP
        // listening endpoint.  Can we make the same assumption for a TCP connecting endpoint?
        let peer_listening_endpoint = (transport == Transport::Utp).then_some(peer_endpoint);

        let span = tracing::info_span!(
            "mgr/accept",
            ?transport,
            cipher = field::Empty,
            ?peer_endpoint,
        );
        Ok((
            peer_endpoint,
            peer_listening_endpoint,
            handshake.instrument(span),
        ))
    }

    async fn handshake<Stream>(
        info_hash: InfoHash,
        self_id: PeerId,
        self_features: Features,
        stream: Stream,
    ) -> Result<Socket, Error>
    where
        Stream: StreamRecv<Error = Error> + StreamSend<Error = Error> + Send + 'static,
    {
        let stream = bittorrent_mse::accept(stream, info_hash.as_ref()).await?;

        let cipher = match stream {
            MseStream::Rc4(_) => Cipher::Mse,
            MseStream::Plaintext(_) => Cipher::Plaintext,
        };
        Span::current().record("cipher", field::debug(&cipher));

        // TODO: Should we look up the peer id if we have connected to this peer before?
        let peer_id = None;

        Socket::accept(stream.into(), info_hash, self_id, self_features, peer_id)
            .await
            .inspect(|socket| tracing::debug!(peer_id = ?socket.peer_id()))
    }
}
