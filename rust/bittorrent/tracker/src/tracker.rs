use std::net::SocketAddr;
use std::sync::Arc;

use futures::future::OptionFuture;
use tokio::{
    sync::watch,
    time::{self, Instant},
};

use g1_tokio::sync::mpmc::{self, error::TrySendError};
use g1_tokio::task::{Cancel, JoinGuard};

use bittorrent_base::{InfoHash, PeerId};
use bittorrent_metainfo::Metainfo;

use crate::{
    client::Client,
    error,
    request::{Event, Request},
    response,
};

// We add `Sync` to `Error` in order to make it convertible to `std::io::Error`.
type Error = Box<dyn std::error::Error + Send + Sync + 'static>;

pub trait Torrent {
    fn num_bytes_send(&self) -> u64;
    fn num_bytes_recv(&self) -> u64;
    fn num_bytes_left(&self) -> u64;
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PeerContactInfo {
    pub id: Option<PeerId>,
    pub endpoint: Endpoint,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Endpoint {
    SocketAddr(SocketAddr),
    DomainName(String, u16),
}

#[derive(Clone, Debug)]
pub struct Tracker {
    // Wrap it in an `Arc` so that `Clone` can be derived for `Tracker`.
    event_send: Arc<watch::Sender<Option<Event>>>,
    peer_recv: mpmc::Receiver<PeerContactInfo>,
}

pub type TrackerGuard = JoinGuard<Result<(), Error>>;

#[derive(Debug)]
struct Actor<T> {
    cancel: Cancel,

    info_hash: InfoHash,
    self_id: PeerId,
    port: u16,
    torrent: T,

    client: Client,
    next_request_at: Option<Instant>,

    event_recv: watch::Receiver<Option<Event>>,
    peer_send: mpmc::Sender<PeerContactInfo>,
}

impl<'a> From<&'a response::PeerContactInfo<'a>> for PeerContactInfo {
    fn from(peer: &'a response::PeerContactInfo<'a>) -> Self {
        Self {
            id: peer.id.map(|id| id.try_into().unwrap()),
            endpoint: (&peer.endpoint).into(),
        }
    }
}

impl<'a> From<&'a response::Endpoint<'a>> for Endpoint {
    fn from(endpoint: &'a response::Endpoint<'a>) -> Self {
        match endpoint {
            response::Endpoint::SocketAddr(endpoint) => Endpoint::SocketAddr(*endpoint),
            response::Endpoint::DomainName(domain_name, port) => {
                Endpoint::DomainName(domain_name.to_string(), *port)
            }
        }
    }
}

impl Tracker {
    pub fn spawn<T>(
        metainfo: &Metainfo,
        info_hash: InfoHash,
        port: u16,
        torrent: T,
    ) -> (Self, TrackerGuard)
    where
        T: Torrent,
        T: Send + 'static,
    {
        let (event_send, event_recv) = watch::channel(None);
        let (peer_send, peer_recv) = mpmc::channel(*crate::peer_queue_size());
        (
            Self {
                event_send: Arc::new(event_send),
                peer_recv,
            },
            JoinGuard::spawn(move |cancel| {
                Actor::new(
                    cancel,
                    metainfo,
                    info_hash,
                    bittorrent_base::self_id().clone(),
                    port,
                    torrent,
                    event_recv,
                    peer_send,
                )
                .run()
            }),
        )
    }

    pub fn start(&self) {
        self.send_event(Some(Event::Started));
    }

    pub fn complete(&self) {
        self.send_event(Some(Event::Completed));
    }

    pub fn stop(&self) {
        self.send_event(Some(Event::Stopped));
    }

    fn send_event(&self, new_event: Option<Event>) {
        self.event_send.send_if_modified(|event| {
            if event == &new_event {
                return false;
            }
            let accept = match event {
                None => true,
                Some(Event::Started) => {
                    matches!(new_event, Some(Event::Completed) | Some(Event::Stopped))
                }
                Some(Event::Completed) => matches!(new_event, Some(Event::Stopped)),
                Some(Event::Stopped) => false,
            };
            if accept {
                *event = new_event;
                true
            } else {
                tracing::warn!(?event, ?new_event, "ignore new event");
                false
            }
        });
    }

    pub async fn next(&self) -> Option<PeerContactInfo> {
        self.peer_recv.recv().await
    }
}

impl<T> Actor<T> {
    #[allow(clippy::too_many_arguments)]
    fn new(
        cancel: Cancel,
        metainfo: &Metainfo,
        info_hash: InfoHash,
        self_id: PeerId,
        port: u16,
        torrent: T,
        event_recv: watch::Receiver<Option<Event>>,
        peer_send: mpmc::Sender<PeerContactInfo>,
    ) -> Self {
        Self {
            cancel,
            info_hash,
            self_id,
            port,
            torrent,
            client: Client::new(metainfo),
            next_request_at: None,
            event_recv,
            peer_send,
        }
    }
}

impl<T> Actor<T>
where
    T: Torrent,
{
    async fn run(mut self) -> Result<(), Error> {
        let mut next_request_at = None;
        tokio::pin! { let timeout = OptionFuture::from(None); }
        loop {
            if next_request_at != self.next_request_at {
                next_request_at = self.next_request_at;
                timeout.set(OptionFuture::from(next_request_at.map(time::sleep_until)));
            }

            tokio::select! {
                () = self.cancel.wait() => break,

                result = self.event_recv.changed() => {
                    // We can call `unwrap` because `event_recv` is never closed.
                    result.unwrap();
                    let event = self.event_recv.borrow_and_update().clone();
                    if matches!(event, Some(Event::Stopped)) {
                        break;
                    } else {
                        self.request(event).await?;
                    }
                }
                Some(()) = &mut timeout => {
                    self.request(None).await?;
                }
            }
        }
        self.request(Some(Event::Stopped)).await
    }

    async fn request(&mut self, event: Option<Event>) -> Result<(), Error> {
        tracing::info!(?event, "->tracker");

        let request = Request::new(
            self.info_hash.clone(),
            self.self_id.clone(),
            self.port,
            self.torrent.num_bytes_send(),
            self.torrent.num_bytes_recv(),
            self.torrent.num_bytes_left(),
            event,
        );

        let response_owner = match self.client.get(&request).await {
            Ok(response_owner) => response_owner,
            Err(error) => {
                if matches!(
                    error.downcast_ref::<error::Error>(),
                    Some(error::Error::AnnounceUrlsFailed),
                ) {
                    return Err(error::Error::AnnounceUrlsFailed.into());
                }
                tracing::warn!(%error, "tracker error");
                return Ok(()); // For now, we ignore all other types of error.
            }
        };
        let response = response_owner.deref();

        self.next_request_at = Some(Instant::now() + response.interval);

        for peer in &response.peers {
            match self.peer_send.try_send(peer.into()) {
                Ok(()) => {}
                Err(TrySendError::Full(peer)) => {
                    tracing::warn!(?peer, "drop peer because queue is full");
                }
                Err(TrySendError::Closed(_)) => break,
            }
        }

        Ok(())
    }
}
