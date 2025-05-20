use bytes::Bytes;
use futures::stream::TryStreamExt;
use std::io::Error;
use tokio::{
    sync::broadcast::{Receiver, error::RecvError},
    time,
};

use g1_tokio::net::{self, udp::OwnedUdpStream};

use bittorrent_base::InfoHash;
use bittorrent_dht::Dht;
use bittorrent_manager::Manager;
use bittorrent_metainfo::InfoOwner;
use bittorrent_peer::Recvs;
use bittorrent_tracker::{Endpoint as TrackerEndpoint, PeerContactInfo, Tracker};
use bittorrent_trackerless::Trackerless;
use bittorrent_transceiver::Update;
use bittorrent_udp::Fork;

pub(crate) async fn fetch_info(
    info_hash: InfoHash,
    manager: &Manager,
    recvs: &mut Recvs,
) -> Result<InfoOwner<Bytes>, Error> {
    let trackerless = Trackerless::new(info_hash, manager, recvs);
    time::timeout(*crate::fetch_info_timeout(), trackerless.fetch())
        .await
        .map_err(|_| Error::other("fetch info timeout"))?
        .map_err(Error::other)
}

pub(crate) async fn make_warm_calls(mut update_recv: Receiver<Update>, manager: Manager) {
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
pub(crate) async fn recruit_from_dht(dht: Dht, info_hash: InfoHash, manager: Manager) {
    let mut interval = time::interval(*crate::dht_lookup_peers_period());
    loop {
        interval.tick().await;
        let (peers, _) = dht.lookup_peers(info_hash.clone()).await;
        for endpoint in peers {
            manager.connect(endpoint, None);
        }
    }
}

pub(crate) async fn update_tracker(mut update_recv: Receiver<Update>, tracker: Tracker) {
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

pub(crate) async fn recruit_from_tracker(tracker: Tracker, manager: Manager) {
    while let Some(PeerContactInfo { id, endpoint }) = tracker.next().await {
        let endpoint = match endpoint {
            TrackerEndpoint::SocketAddr(endpoint) => endpoint,
            TrackerEndpoint::DomainName(ref domain_name, port) => {
                match net::lookup_host_first((domain_name.as_str(), port)).await {
                    Ok(endpoint) => endpoint,
                    Err(error) => {
                        tracing::warn!(?id, ?endpoint, %error, "peer endpoint resolution error");
                        continue;
                    }
                }
            }
        };
        manager.connect(endpoint, id);
    }
}

pub(crate) async fn handle_udp_error(
    mut udp_error_stream: Fork<OwnedUdpStream>,
) -> Result<(), Error> {
    while let Some((peer_endpoint, payload)) = udp_error_stream.try_next().await? {
        tracing::warn!(?peer_endpoint, ?payload, "receive unrecognizable payload");
    }
    Ok(())
}
