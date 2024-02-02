use std::io::Error;
use std::net::SocketAddr;
use std::pin::Pin;
use std::sync::Arc;

use bytes::Bytes;
use futures::{future::OptionFuture, sink::Sink, stream::Stream};
use tokio::net::{TcpListener, TcpSocket, UdpSocket};

use g1_base::fmt::{DebugExt, InsertPlaceholder};
use g1_futures::sink;
use g1_tokio::net::udp::{self, OwnedUdpSink, OwnedUdpStream};

use bittorrent_base::{Features, InfoHash};
use bittorrent_dht::Agent as DhtAgent;
use bittorrent_manager::Manager;
use bittorrent_peer::Recvs;
use bittorrent_utp::UtpSocket;

// TODO: Can we remove these `Pin`?
type DynStream = Pin<Box<dyn Stream<Item = Result<(SocketAddr, Bytes), Error>> + Send + 'static>>;
type DynSink = Pin<Box<dyn Sink<(SocketAddr, Bytes), Error = Error> + Send + 'static>>;

pub(crate) type Fork = bittorrent_udp::Fork<OwnedUdpStream>;
type Fanin = sink::Fanin<OwnedUdpSink>;

#[derive(Debug)]
pub(crate) struct Init {
    info_hash: InfoHash,

    manager: Option<Arc<Manager>>,
    recvs: Option<Recvs>,

    net_ipv4: Option<NetInit>,
    net_ipv6: Option<NetInit>,
}

#[derive(DebugExt)]
struct NetInit {
    self_endpoint: SocketAddr,
    self_features: Features,

    dht: Option<Arc<DhtAgent>>,
    dht_stream: Option<Fork>,
    dht_sink: Option<Fanin>,

    utp_socket: Option<Arc<UtpSocket>>,
    #[debug(with = InsertPlaceholder)]
    utp_stream: Option<DynStream>,
    #[debug(with = InsertPlaceholder)]
    utp_sink: Option<DynSink>,

    udp_socket: Option<Arc<UdpSocket>>,
    udp_stream_and_sink_init: bool,
    udp_error_stream: Option<Fork>,
}

macro_rules! call {
    ($net:expr, $func:ident $(,)?) => {
        OptionFuture::from($net.as_mut().map(|net| net.$func()))
            .await
            .transpose()?
    };
}

impl Init {
    pub(crate) fn new_default(info_hash: InfoHash) -> Self {
        Self::new(
            info_hash,
            *crate::self_endpoint_ipv4(),
            *crate::self_endpoint_ipv6(),
            Features::load(),
        )
    }

    pub(crate) fn new(
        info_hash: InfoHash,
        self_endpoint_ipv4: Option<SocketAddr>,
        self_endpoint_ipv6: Option<SocketAddr>,
        self_features: Features,
    ) -> Self {
        let to_net = |self_endpoint| NetInit::new(self_endpoint, self_features);
        Self {
            info_hash,

            manager: None,
            recvs: None,

            net_ipv4: self_endpoint_ipv4.map(to_net),
            net_ipv6: self_endpoint_ipv6.map(to_net),
        }
    }

    pub(crate) fn port_ipv4(&self) -> Option<u16> {
        self.net_ipv4.as_ref().map(|net| net.self_endpoint.port())
    }

    //
    // Manager
    //

    pub(crate) async fn init_manager(&mut self) -> Result<Arc<Manager>, Error> {
        self.init_manager_and_recvs().await?;
        Ok(self.manager.clone().unwrap())
    }

    pub(crate) async fn init_once_recvs(&mut self) -> Result<Recvs, Error> {
        self.init_manager_and_recvs().await?;
        Ok(self.recvs.take().unwrap())
    }

    async fn init_manager_and_recvs(&mut self) -> Result<(), Error> {
        if self.manager.is_none() {
            tracing::info!(
                self_endpoint_ipv4 = ?self.net_ipv4.as_ref().map(|net| net.self_endpoint),
                self_endpoint_ipv6 = ?self.net_ipv6.as_ref().map(|net| net.self_endpoint),
                "init peer manager",
            );
            let (manager, recvs) = Manager::new(
                self.info_hash.clone(),
                call!(self.net_ipv4, new_tcp_listener),
                call!(self.net_ipv6, new_tcp_listener),
                call!(self.net_ipv4, init_utp_socket),
                call!(self.net_ipv6, init_utp_socket),
            );
            self.manager = Some(Arc::new(manager));
            self.recvs = Some(recvs);
        }
        Ok(())
    }

    //
    // DHT
    //

    pub(crate) async fn init_dht_ipv4(&mut self) -> Result<Option<Arc<DhtAgent>>, Error> {
        Ok(call!(self.net_ipv4, init_dht).flatten())
    }

    pub(crate) async fn init_dht_ipv6(&mut self) -> Result<Option<Arc<DhtAgent>>, Error> {
        Ok(call!(self.net_ipv6, init_dht).flatten())
    }

    //
    // UDP
    //

    pub(crate) async fn init_once_udp_error_stream_ipv4(&mut self) -> Result<Option<Fork>, Error> {
        Ok(call!(self.net_ipv4, init_once_udp_error_stream).flatten())
    }

    pub(crate) async fn init_once_udp_error_stream_ipv6(&mut self) -> Result<Option<Fork>, Error> {
        Ok(call!(self.net_ipv6, init_once_udp_error_stream).flatten())
    }
}

impl NetInit {
    fn new(self_endpoint: SocketAddr, self_features: Features) -> Self {
        Self {
            self_endpoint,
            self_features,

            dht: None,
            dht_stream: None,
            dht_sink: None,

            utp_socket: None,
            utp_stream: None,
            utp_sink: None,

            udp_socket: None,
            udp_stream_and_sink_init: false,
            udp_error_stream: None,
        }
    }

    //
    // TcpListener
    //

    async fn new_tcp_listener(&self) -> Result<TcpListener, Error> {
        let socket = if self.self_endpoint.is_ipv4() {
            TcpSocket::new_v4()
        } else {
            assert!(self.self_endpoint.is_ipv6());
            TcpSocket::new_v6()
        }?;
        socket.set_reuseport(true)?;
        socket.bind(self.self_endpoint)?;
        socket.listen(*crate::tcp_listen_backlog())
    }

    //
    // DHT
    //

    async fn init_dht(&mut self) -> Result<Option<Arc<DhtAgent>>, Error> {
        if !self.self_features.dht {
            return Ok(None);
        }
        if self.dht.is_none() {
            tracing::info!(self_endpoint = ?self.self_endpoint, "init dht agent");
            self.dht = Some(Arc::new(DhtAgent::new_default(
                self.self_endpoint,
                self.init_once_dht_stream().await?,
                self.init_once_dht_sink().await?,
            )));
        }
        Ok(self.dht.clone())
    }

    async fn init_once_dht_stream(&mut self) -> Result<Fork, Error> {
        self.init_udp_stream_and_sink().await?;
        Ok(self.dht_stream.take().unwrap())
    }

    async fn init_once_dht_sink(&mut self) -> Result<Fanin, Error> {
        self.init_udp_stream_and_sink().await?;
        Ok(self.dht_sink.take().unwrap())
    }

    //
    // UtpSocket
    //

    async fn init_utp_socket(&mut self) -> Result<Arc<UtpSocket>, Error> {
        if self.utp_socket.is_none() {
            self.utp_socket = Some(Arc::new(UtpSocket::new(
                self.init_udp_socket().await?,
                self.init_once_utp_stream().await?,
                self.init_once_utp_sink().await?,
            )));
        }
        Ok(self.utp_socket.clone().unwrap())
    }

    async fn init_once_utp_stream(&mut self) -> Result<DynStream, Error> {
        self.init_udp_stream_and_sink().await?;
        Ok(self.utp_stream.take().unwrap())
    }

    async fn init_once_utp_sink(&mut self) -> Result<DynSink, Error> {
        self.init_udp_stream_and_sink().await?;
        Ok(self.utp_sink.take().unwrap())
    }

    //
    // UDP
    //

    async fn init_udp_socket(&mut self) -> Result<Arc<UdpSocket>, Error> {
        if self.udp_socket.is_none() {
            // TODO: Do we need to call `set_reuseport(true)` on UDP sockets?
            self.udp_socket = Some(Arc::new(UdpSocket::bind(self.self_endpoint).await?));
        }
        Ok(self.udp_socket.clone().unwrap())
    }

    async fn init_once_udp_error_stream(&mut self) -> Result<Option<Fork>, Error> {
        self.init_udp_stream_and_sink().await?;
        Ok(self.udp_error_stream.take())
    }

    async fn init_udp_stream_and_sink(&mut self) -> Result<(), Error> {
        if !self.udp_stream_and_sink_init {
            let (stream, sink) = udp::UdpSocket::new(self.init_udp_socket().await?).into_split();

            if self.self_features.dht {
                let (dht_stream, utp_stream, udp_error_stream) = bittorrent_udp::fork(stream);
                self.dht_stream = Some(dht_stream);
                self.utp_stream = Some(Box::pin(utp_stream));
                self.udp_error_stream = Some(udp_error_stream);

                let [dht_sink, utp_sink] = sink::fanin(sink);
                self.dht_sink = Some(dht_sink);
                self.utp_sink = Some(Box::pin(utp_sink));
            } else {
                self.utp_stream = Some(Box::pin(stream));
                self.utp_sink = Some(Box::pin(sink));
            }

            self.udp_stream_and_sink_init = true;
        }
        Ok(())
    }
}
