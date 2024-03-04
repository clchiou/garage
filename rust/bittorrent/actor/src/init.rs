use std::io::Error;
use std::net::SocketAddr;
use std::pin::Pin;
use std::sync::Arc;

use bytes::Bytes;
use futures::{future::OptionFuture, sink::Sink, stream::Stream};
use tokio::net::{TcpListener, TcpSocket, UdpSocket};
use tokio::sync::broadcast::Receiver;

use g1_base::fmt::{DebugExt, InsertPlaceholder};
use g1_futures::sink;
use g1_tokio::net::udp::{self, OwnedUdpSink, OwnedUdpStream};
use g1_tokio::task::{JoinGuard, JoinQueue};

use bittorrent_base::{Dimension, Features, InfoHash};
use bittorrent_dht::{Dht, DhtGuard};
use bittorrent_manager::{Manager, ManagerGuard};
use bittorrent_metainfo::Info;
use bittorrent_peer::Recvs;
use bittorrent_tracker::{Tracker, TrackerGuard};
use bittorrent_transceiver::{
    DynStorage, Torrent, Transceiver, TransceiverGuard, TransceiverSpawn, Update,
};
use bittorrent_utp::UtpSocket;

use crate::integrate;
use crate::storage::StorageOpen;
use crate::Mode;

// TODO: Can we remove these `Pin`?
type DynStream = Pin<Box<dyn Stream<Item = Result<(SocketAddr, Bytes), Error>> + Send + 'static>>;
type DynSink = Pin<Box<dyn Sink<(SocketAddr, Bytes), Error = Error> + Send + 'static>>;

pub(crate) type Fork = bittorrent_udp::Fork<OwnedUdpStream>;
type Fanin = sink::Fanin<OwnedUdpSink>;

#[derive(DebugExt)]
pub(crate) struct Init {
    mode: Mode,
    info_hash: InfoHash,
    open: StorageOpen,

    txrx: Option<Transceiver>,
    txrx_guard: Option<TransceiverGuard>,
    #[debug(with = InsertPlaceholder)]
    txrx_spawn: Option<TransceiverSpawn>,
    torrent: Option<Torrent>,
    update_recv: Option<Receiver<Update>>,

    manager: Option<Manager>,
    recvs: Option<Recvs>,
    manager_guard: Option<ManagerGuard>,

    tracker: Option<Tracker>,
    tracker_guard: Option<Option<TrackerGuard>>,

    net_ipv4: Option<NetInit>,
    net_ipv6: Option<NetInit>,

    tasks: Arc<JoinQueue<Result<(), Error>>>,
}

#[derive(Debug)]
pub(crate) struct Guards {
    pub(crate) txrx_guard: TransceiverGuard,

    pub(crate) manager_guard: ManagerGuard,

    pub(crate) dht_guard_ipv4: Option<DhtGuard>,
    pub(crate) dht_guard_ipv6: Option<DhtGuard>,

    pub(crate) tracker_guard: Option<TrackerGuard>,

    pub(crate) utp_socket_ipv4: Option<UtpSocket>,
    pub(crate) utp_socket_ipv6: Option<UtpSocket>,

    pub(crate) tasks: JoinQueue<Result<(), Error>>,
}

#[derive(DebugExt)]
struct NetInit {
    info_hash: InfoHash,
    self_endpoint: SocketAddr,
    self_features: Features,

    dht: Option<Dht>,
    dht_guard: Option<DhtGuard>,
    dht_stream: Option<Fork>,
    dht_sink: Option<Fanin>,

    utp_socket: Option<UtpSocket>,
    #[debug(with = InsertPlaceholder)]
    utp_stream: Option<DynStream>,
    #[debug(with = InsertPlaceholder)]
    utp_sink: Option<DynSink>,

    udp_socket: Option<Arc<UdpSocket>>,
    udp_stream_and_sink_init: bool,

    tasks: Arc<JoinQueue<Result<(), Error>>>,
}

macro_rules! subinit {
    ($sub:expr, $init:ident ( $($args:expr),* $(,)? ) $(,)?) => {
        OptionFuture::from($sub.as_mut().map(|sub| sub.$init($($args),*)))
            .await
            .transpose()?
    };
}

impl Init {
    pub(crate) fn new(mode: Mode, info_hash: InfoHash, open: StorageOpen) -> Self {
        Self::with_params(
            mode,
            info_hash,
            open,
            *crate::self_endpoint_ipv4(),
            *crate::self_endpoint_ipv6(),
            Features::load(),
        )
    }

    pub(crate) fn with_params(
        mode: Mode,
        info_hash: InfoHash,
        open: StorageOpen,
        self_endpoint_ipv4: Option<SocketAddr>,
        self_endpoint_ipv6: Option<SocketAddr>,
        self_features: Features,
    ) -> Self {
        let tasks = Arc::new(JoinQueue::new());
        let net_init_new = |self_endpoint| {
            NetInit::new(
                info_hash.clone(),
                self_endpoint,
                self_features,
                tasks.clone(),
            )
        };
        let net_ipv4 = self_endpoint_ipv4.map(net_init_new);
        let net_ipv6 = self_endpoint_ipv6.map(net_init_new);
        Self {
            mode,
            info_hash,
            open,

            txrx: None,
            txrx_guard: None,
            txrx_spawn: None,
            torrent: None,
            update_recv: None,

            manager: None,
            recvs: None,
            manager_guard: None,

            tracker: None,
            tracker_guard: None,

            net_ipv4,
            net_ipv6,

            tasks,
        }
    }

    fn self_endpoint_ipv4(&self) -> Option<SocketAddr> {
        self.net_ipv4.as_ref().map(|net| net.self_endpoint)
    }

    fn self_endpoint_ipv6(&self) -> Option<SocketAddr> {
        self.net_ipv6.as_ref().map(|net| net.self_endpoint)
    }

    fn port_ipv4(&self) -> Option<u16> {
        self.self_endpoint_ipv4()
            .map(|self_endpoint| self_endpoint.port())
    }

    pub(crate) async fn into_guards(mut self) -> Result<Guards, Error> {
        self.init_txrx_guard().await?;
        let manager = self.init_manager().await?;
        subinit!(self.net_ipv4, init_dht_guard(manager.clone()));
        subinit!(self.net_ipv6, init_dht_guard(manager));
        self.init_tracker_guard().await?;
        subinit!(self.net_ipv4, init_utp_socket());
        subinit!(self.net_ipv6, init_utp_socket());

        let Self {
            txrx_guard,
            manager_guard,
            tracker_guard,
            mut net_ipv4,
            mut net_ipv6,
            tasks,
            ..
        } = self;
        let dht_guard_ipv4 = net_ipv4.as_mut().and_then(|net| net.dht_guard.take());
        let dht_guard_ipv6 = net_ipv6.as_mut().and_then(|net| net.dht_guard.take());
        let utp_socket_ipv4 = net_ipv4.as_mut().map(|net| net.utp_socket.take().unwrap());
        let utp_socket_ipv6 = net_ipv6.as_mut().map(|net| net.utp_socket.take().unwrap());
        // Drop `tasks` clones.
        drop(net_ipv4);
        drop(net_ipv6);

        Ok(Guards {
            txrx_guard: txrx_guard.unwrap(),

            manager_guard: manager_guard.unwrap(),

            dht_guard_ipv4,
            dht_guard_ipv6,

            tracker_guard: tracker_guard.unwrap(),

            utp_socket_ipv4,
            utp_socket_ipv6,

            tasks: Arc::into_inner(tasks).unwrap(),
        })
    }

    //
    // Transceiver
    //

    pub(crate) async fn init_txrx(&mut self) -> Result<Transceiver, Error> {
        self.init_txrx_guard().await?;
        Ok(self.txrx.clone().unwrap())
    }

    async fn init_txrx_guard(&mut self) -> Result<(), Error> {
        if self.txrx_guard.is_some() {
            return Ok(());
        }

        self.init_txrx_spawn().await?;

        tracing::info!("spawn txrx");
        let (txrx, txrx_guard) = self.txrx_spawn.take().unwrap()();

        self.txrx = Some(txrx);
        self.txrx_guard = Some(txrx_guard);
        Ok(())
    }

    async fn init_torrent(&mut self) -> Result<Torrent, Error> {
        self.init_txrx_spawn().await?;
        Ok(self.torrent.clone().unwrap())
    }

    async fn init_once_update_recv(&mut self) -> Result<Receiver<Update>, Error> {
        self.init_txrx_spawn().await?;
        Ok(self.update_recv.take().unwrap())
    }

    async fn init_txrx_spawn(&mut self) -> Result<(), Error> {
        // Check `torrent` instead of `txrx_spawn` because the former is not moved out.
        if self.torrent.is_some() {
            return Ok(());
        }

        let manager = self.init_manager().await?;
        let mut recvs = self.init_once_recvs().await?;
        let dht_ipv4 = self.init_dht_ipv4().await?;
        let dht_ipv6 = self.init_dht_ipv6().await?;

        async fn open(
            open: &StorageOpen,
            info: &Info<'_>,
        ) -> Result<(Bytes, Dimension, DynStorage), Error> {
            // `MetainfoOwner` and `InfoOwner` do not guarantee that their buffers exactly match
            // the raw info blob.  Therefore, we cannot rely on the `into_buffer` method and must
            // explicitly copy the blob.
            let raw_info = Bytes::copy_from_slice(info.raw_info);
            let dim = info.new_dimension(*bittorrent_base::block_size());
            let storage = open.open(info, dim.clone()).await?;
            Ok((raw_info, dim, storage))
        }
        let (raw_info, dim, storage) = match &self.mode {
            Mode::Tracker(metainfo) => open(&self.open, &metainfo.deref().info).await?,
            Mode::Trackerless(Some(info)) => open(&self.open, info.deref()).await?,
            Mode::Trackerless(None) => {
                if dht_ipv4.is_none() && dht_ipv6.is_none() {
                    return Err(Error::other("fetch_info requires dht"));
                }
                open(
                    &self.open,
                    integrate::fetch_info(self.info_hash.clone(), &manager, &mut recvs)
                        .await?
                        .deref(),
                )
                .await?
            }
        };

        tracing::info!("prepare txrx");
        let (txrx_spawn, torrent, update_recv) = Transceiver::prepare_spawn(
            raw_info,
            dim,
            manager.clone(),
            recvs,
            storage,
            dht_ipv4,
            dht_ipv6,
        )
        .await?;

        {
            let update_recv = update_recv.resubscribe();
            let _ = self.tasks.push(JoinGuard::spawn(move |cancel| async move {
                tokio::select! {
                    () = cancel.wait() => {}
                    () = integrate::make_warm_calls(update_recv, manager) => {}
                }
                Ok(())
            }));
        }

        self.txrx_spawn = Some(txrx_spawn);
        self.torrent = Some(torrent);
        self.update_recv = Some(update_recv);
        Ok(())
    }

    //
    // Manager
    //

    pub(crate) async fn init_manager(&mut self) -> Result<Manager, Error> {
        self.init_manager_guard().await?;
        Ok(self.manager.clone().unwrap())
    }

    async fn init_once_recvs(&mut self) -> Result<Recvs, Error> {
        self.init_manager_guard().await?;
        Ok(self.recvs.take().unwrap())
    }

    async fn init_manager_guard(&mut self) -> Result<(), Error> {
        if self.manager_guard.is_some() {
            return Ok(());
        }

        tracing::info!(
            self_endpoint_ipv4 = ?self.self_endpoint_ipv4(),
            self_endpoint_ipv6 = ?self.self_endpoint_ipv6(),
            "init peer manager",
        );
        let (manager, recvs, manager_guard) = Manager::spawn(
            self.info_hash.clone(),
            subinit!(self.net_ipv4, new_tcp_listener()),
            subinit!(self.net_ipv6, new_tcp_listener()),
            subinit!(self.net_ipv4, init_utp_socket()),
            subinit!(self.net_ipv6, init_utp_socket()),
        );

        for &peer_endpoint in crate::peer_endpoints() {
            manager.connect(peer_endpoint, None);
        }

        self.manager = Some(manager);
        self.recvs = Some(recvs);
        self.manager_guard = Some(manager_guard);
        Ok(())
    }

    //
    // DHT
    //

    pub(crate) async fn init_dht_ipv4(&mut self) -> Result<Option<Dht>, Error> {
        let manager = self.init_manager().await?;
        Ok(subinit!(self.net_ipv4, init_dht(manager)).flatten())
    }

    pub(crate) async fn init_dht_ipv6(&mut self) -> Result<Option<Dht>, Error> {
        let manager = self.init_manager().await?;
        Ok(subinit!(self.net_ipv6, init_dht(manager)).flatten())
    }

    //
    // Tracker
    //

    pub(crate) async fn init_tracker(&mut self) -> Result<Option<Tracker>, Error> {
        self.init_tracker_guard().await?;
        Ok(self.tracker.clone())
    }

    async fn init_tracker_guard(&mut self) -> Result<(), Error> {
        if self.tracker_guard.is_some() {
            return Ok(());
        }
        if matches!(self.mode, Mode::Trackerless(_)) {
            self.tracker_guard = Some(None);
            return Ok(());
        }

        let torrent = self.init_torrent().await?;
        let update_recv = self.init_once_update_recv().await?;
        let manager = self.init_manager().await?;
        let Mode::Tracker(metainfo) = &self.mode else {
            std::unreachable!()
        };

        tracing::info!("init tracker");
        let (tracker, tracker_guard) = Tracker::spawn(
            metainfo.deref(),
            self.info_hash.clone(),
            self.port_ipv4().unwrap(),
            torrent,
        );

        {
            let tracker = tracker.clone();
            let _ = self.tasks.push(JoinGuard::spawn(move |cancel| async move {
                tokio::select! {
                    () = cancel.wait() => {}
                    () = integrate::update_tracker(update_recv, tracker) => {}
                }
                Ok(())
            }));
        }

        {
            let tracker = tracker.clone();
            let _ = self.tasks.push(JoinGuard::spawn(move |cancel| async move {
                tokio::select! {
                    () = cancel.wait() => {}
                    () = integrate::recruit_from_tracker(tracker, manager) => {}
                }
                Ok(())
            }));
        }

        self.tracker = Some(tracker);
        self.tracker_guard = Some(Some(tracker_guard));
        Ok(())
    }
}

impl NetInit {
    fn new(
        info_hash: InfoHash,
        self_endpoint: SocketAddr,
        self_features: Features,
        tasks: Arc<JoinQueue<Result<(), Error>>>,
    ) -> Self {
        Self {
            info_hash,
            self_endpoint,
            self_features,

            dht: None,
            dht_guard: None,
            dht_stream: None,
            dht_sink: None,

            utp_socket: None,
            utp_stream: None,
            utp_sink: None,

            udp_socket: None,
            udp_stream_and_sink_init: false,

            tasks,
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

    async fn init_dht(&mut self, manager: Manager) -> Result<Option<Dht>, Error> {
        self.init_dht_guard(manager).await?;
        Ok(self.dht.clone())
    }

    async fn init_dht_guard(&mut self, manager: Manager) -> Result<(), Error> {
        if !self.self_features.dht || self.dht.is_some() {
            return Ok(());
        }

        tracing::info!(self_endpoint = ?self.self_endpoint, "init dht");
        let (dht, dht_guard) = Dht::spawn(
            self.self_endpoint,
            self.init_once_dht_stream().await?,
            self.init_once_dht_sink().await?,
        );

        {
            let dht = dht.clone();
            let info_hash = self.info_hash.clone();
            let _ = self.tasks.push(JoinGuard::spawn(move |cancel| async move {
                tokio::select! {
                    () = cancel.wait() => {}
                    () = integrate::recruit_from_dht(dht, info_hash, manager) => {}
                }
                Ok(())
            }));
        }

        self.dht = Some(dht);
        self.dht_guard = Some(dht_guard);
        Ok(())
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

    async fn init_utp_socket(&mut self) -> Result<&UtpSocket, Error> {
        if self.utp_socket.is_none() {
            self.utp_socket = Some(UtpSocket::new(
                self.init_udp_socket().await?,
                self.init_once_utp_stream().await?,
                self.init_once_utp_sink().await?,
            ));
        }
        Ok(self.utp_socket.as_ref().unwrap())
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

    async fn init_udp_stream_and_sink(&mut self) -> Result<(), Error> {
        if self.udp_stream_and_sink_init {
            return Ok(());
        }

        let (stream, sink) = udp::UdpSocket::new(self.init_udp_socket().await?).into_split();

        if self.self_features.dht {
            let (dht_stream, utp_stream, udp_error_stream) = bittorrent_udp::fork(stream);
            let [dht_sink, utp_sink] = sink::fanin(sink);

            let _ = self.tasks.push(JoinGuard::spawn(move |cancel| async move {
                tokio::select! {
                    () = cancel.wait() => Ok(()),
                    result = integrate::handle_udp_error(udp_error_stream) => result,
                }
            }));

            self.dht_stream = Some(dht_stream);
            self.utp_stream = Some(Box::pin(utp_stream));

            self.dht_sink = Some(dht_sink);
            self.utp_sink = Some(Box::pin(utp_sink));
        } else {
            self.utp_stream = Some(Box::pin(stream));
            self.utp_sink = Some(Box::pin(sink));
        }

        self.udp_stream_and_sink_init = true;
        Ok(())
    }
}
