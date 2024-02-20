use std::io::Error;
use std::sync::Arc;

use bytes::Bytes;
use futures::{future::OptionFuture, stream::TryStreamExt};
use tokio::{
    sync::broadcast::{error::RecvError, Receiver},
    time,
};

use g1_tokio::{
    net::{self, udp::OwnedUdpStream},
    task::{Cancel, JoinGuard, JoinQueue},
};

use bittorrent_base::{Dimension, InfoHash};
use bittorrent_dht::{Dht, DhtGuard};
use bittorrent_manager::Manager;
use bittorrent_metainfo::{Info, InfoOwner, MetainfoOwner};
use bittorrent_peer::Recvs;
use bittorrent_tracker::{Agent as TrackerAgent, Endpoint as TrackerEndpoint, PeerContactInfo};
use bittorrent_trackerless::Trackerless;
use bittorrent_transceiver::{Agent as TxrxAgent, DynStorage, Init as TxrxAgentInit, Update};
use bittorrent_udp::Fork;

use crate::{net::Init, storage::StorageOpen};

#[derive(Debug)]
pub struct Agents {
    pub txrx: TxrxAgent,
    pub manager: Arc<Manager>,
    pub dht_ipv4: Option<Dht>,
    pub dht_ipv6: Option<Dht>,
    pub tracker: Option<Arc<TrackerAgent>>,

    dht_guard_ipv4: Option<DhtGuard>,
    dht_guard_ipv6: Option<DhtGuard>,
    tasks: JoinQueue<Result<(), Error>>,
}

#[derive(Debug)]
pub enum Mode {
    Tracker(MetainfoOwner<Bytes>),
    Trackerless(Option<InfoOwner<Bytes>>),
}

#[derive(Debug)]
struct TorrentInit {
    open: StorageOpen,
}

impl Agents {
    pub async fn make(mode: Mode, info_hash: InfoHash, open: StorageOpen) -> Result<Self, Error> {
        let mut net_init = Init::new_default(info_hash.clone());
        let torrent_init = TorrentInit::new(open);

        let manager = net_init.init_manager().await?;
        let mut recvs = net_init.init_once_recvs().await?;
        let dht_ipv4 = net_init.init_dht_ipv4().await?;
        let dht_ipv6 = net_init.init_dht_ipv6().await?;
        // TODO: Implement cooperative cancellation.
        let tasks = JoinQueue::with_cancel(Cancel::new());

        for &peer_endpoint in crate::peer_endpoints() {
            manager.connect(peer_endpoint, None);
        }

        for dht in [dht_ipv4.clone(), dht_ipv6.clone()].into_iter().flatten() {
            let info_hash = info_hash.clone();
            let manager = manager.clone();
            let _ = tasks.push(JoinGuard::spawn(move |cancel| async move {
                tokio::select! {
                    _ = recruit_from_dht(dht, info_hash, manager) => {}
                    _ = cancel.wait() => {}
                }
                Ok(())
            }));
        }
        for udp_error_stream in [
            net_init.init_once_udp_error_stream_ipv4().await?,
            net_init.init_once_udp_error_stream_ipv6().await?,
        ]
        .into_iter()
        .flatten()
        {
            let _ = tasks.push(JoinGuard::spawn(move |cancel| async move {
                tokio::select! {
                    result = handle_udp_error(udp_error_stream) => result,
                    _ = cancel.wait() => Ok(()),
                }
            }));
        }

        let (metainfo, (raw_info, dim, storage)) = match mode {
            Mode::Tracker(metainfo) => {
                let torrent = torrent_init.init(&metainfo.deref().info).await?;
                (Some(metainfo), torrent)
            }
            Mode::Trackerless(info) => {
                let info = match info {
                    Some(info) => info,
                    None => fetch_metadata(info_hash.clone(), &manager, &mut recvs).await?,
                };
                let torrent = torrent_init.init(info.deref()).await?;
                (None, torrent)
            }
        };

        let txrx_init = TxrxAgentInit::make(
            raw_info,
            dim,
            manager.clone(),
            recvs,
            storage,
            dht_ipv4.clone(),
            dht_ipv6.clone(),
        )
        .await?;

        {
            let manager = manager.clone();
            let update_recv = txrx_init.subscribe();
            let _ = tasks.push(JoinGuard::spawn(move |cancel| async move {
                tokio::select! {
                    _ = make_warm_calls(update_recv, manager) => {}
                    _ = cancel.wait() => {}
                }
                Ok(())
            }));
        }

        let tracker = metainfo.map(|metainfo| {
            Arc::new(TrackerAgent::new(
                metainfo.deref(),
                info_hash,
                net_init.port_ipv4().unwrap(),
                txrx_init.torrent.clone(),
            ))
        });

        if let Some(tracker) = tracker.clone() {
            {
                let tracker = tracker.clone();
                let update_recv = txrx_init.subscribe();
                let _ = tasks.push(JoinGuard::spawn(move |cancel| async move {
                    tokio::select! {
                        _ = update_tracker(update_recv, tracker) => {}
                        _ = cancel.wait() => {}
                    }
                    Ok(())
                }));
            }
            let manager = manager.clone();
            let _ = tasks.push(JoinGuard::spawn(move |cancel| async move {
                tokio::select! {
                    _ = recruit_from_tracker(tracker, manager) => {}
                    _ = cancel.wait() => {}
                }
                Ok(())
            }));
        }

        Ok(Self {
            txrx: txrx_init.into(),
            manager,
            dht_ipv4,
            dht_ipv6,
            tracker,

            dht_guard_ipv4: net_init.init_once_dht_guard_ipv4().await?,
            dht_guard_ipv6: net_init.init_once_dht_guard_ipv6().await?,
            tasks,
        })
    }

    pub async fn join_any(&mut self) {
        macro_rules! join {
            ($guard:ident $(,)?) => {
                OptionFuture::from(self.$guard.as_mut().map(|guard| guard.join()))
            };
        }
        tokio::select! {
            _ = self.txrx.join() => {}
            Some(()) = join!(dht_guard_ipv4) => {}
            Some(()) = join!(dht_guard_ipv6) => {}
            _ = self.tasks.joinable() => {}
        }
    }

    pub async fn shutdown_all(&mut self) -> Result<(), Error> {
        macro_rules! shutdown {
            ($guard:ident $(,)?) => {
                match OptionFuture::from(self.$guard.as_mut().map(|guard| guard.shutdown())).await {
                    Some(join_result) => join_result?,
                    None => Ok(()),
                }
            };
        }
        self.tasks.cancel();
        tokio::try_join!(
            self.txrx.shutdown(),
            self.manager.shutdown(),
            async { shutdown!(dht_guard_ipv4) },
            async { shutdown!(dht_guard_ipv6) },
            async {
                match self.tracker.as_ref() {
                    Some(tracker) => tracker.shutdown().await.map_err(Error::other),
                    None => Ok(()),
                }
            },
            async { self.tasks.shutdown().await? },
        )?;
        Ok(())
    }
}

impl TorrentInit {
    fn new(open: StorageOpen) -> Self {
        Self { open }
    }

    async fn init(self, info: &Info<'_>) -> Result<(Bytes, Dimension, DynStorage), Error> {
        // `MetainfoOwner` and `InfoOwner` do not guarantee that their buffers exactly match the
        // raw info blob.  Therefore, we cannot rely on the `into_buffer` method and must
        // explicitly copy the blob.
        let raw_info = Bytes::copy_from_slice(info.raw_info);
        let dim = info.new_dimension(*bittorrent_base::block_size());
        let storage = self.open.open(info, dim.clone()).await?;
        Ok((raw_info, dim, storage))
    }
}

async fn fetch_metadata(
    info_hash: InfoHash,
    manager: &Manager,
    recvs: &mut Recvs,
) -> Result<InfoOwner<Bytes>, Error> {
    let trackerless = Trackerless::new(info_hash, manager, recvs);
    time::timeout(*crate::fetch_metadata_timeout(), trackerless.fetch())
        .await
        .map_err(|_| Error::other("fetch metadata timeout"))?
        .map_err(Error::other)
}

async fn make_warm_calls(mut update_recv: Receiver<Update>, manager: Arc<Manager>) {
    loop {
        match update_recv.recv().await {
            Ok(Update::Idle) => {
                // If, after making a round of warm calls, we still cannot connect to any peers,
                // what else can we do?
                tracing::info!("make warm calls");
                for peer_endpoint in manager.peer_endpoints() {
                    manager.connect(peer_endpoint, None);
                }
            }
            Ok(_) => {} // Do nothing here.
            Err(RecvError::Lagged(num_skipped)) => {
                // TODO: Should we return an error instead?
                tracing::warn!(num_skipped, "lag behind on txrx updates");
            }
            Err(RecvError::Closed) => break,
        }
    }
}

// NOTE: This never exits.  You have to abort it.
async fn recruit_from_dht(dht: Dht, info_hash: InfoHash, manager: Arc<Manager>) {
    let mut interval = time::interval(*crate::dht_lookup_peers_period());
    loop {
        interval.tick().await;
        let (peers, _) = dht.lookup_peers(info_hash.clone()).await;
        for endpoint in peers {
            manager.connect(endpoint, None);
        }
    }
}

async fn update_tracker(mut update_recv: Receiver<Update>, tracker: Arc<TrackerAgent>) {
    loop {
        match update_recv.recv().await {
            Ok(update) => {
                match update {
                    Update::Start => tracker.start(),
                    Update::Download(_) | Update::Idle => {} // Do nothing here.
                    Update::Complete => tracker.complete(),
                    Update::Stop => {
                        tracker.stop();
                        break;
                    }
                }
            }
            Err(RecvError::Lagged(num_skipped)) => {
                // TODO: Should we return an error instead?
                tracing::warn!(num_skipped, "lag behind on txrx updates");
            }
            Err(RecvError::Closed) => break,
        }
    }
}

async fn recruit_from_tracker(tracker: Arc<TrackerAgent>, manager: Arc<Manager>) {
    while let Some(PeerContactInfo { id, endpoint }) = tracker.next().await {
        let endpoint = match endpoint {
            TrackerEndpoint::SocketAddr(endpoint) => endpoint,
            TrackerEndpoint::DomainName(ref domain_name, port) => {
                match net::lookup_host_first((domain_name.as_str(), port)).await {
                    Ok(endpoint) => endpoint,
                    Err(error) => {
                        tracing::warn!(?id, ?endpoint, ?error, "peer endpoint resolution error");
                        continue;
                    }
                }
            }
        };
        manager.connect(endpoint, id);
    }
}

async fn handle_udp_error(mut udp_error_stream: Fork<OwnedUdpStream>) -> Result<(), Error> {
    while let Some((peer_endpoint, payload)) = udp_error_stream.try_next().await? {
        tracing::warn!(?peer_endpoint, ?payload, "receive unrecognizable payload");
    }
    Ok(())
}
