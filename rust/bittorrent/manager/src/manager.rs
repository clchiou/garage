use std::io::Error;
use std::sync::{Arc, Mutex};

use tokio::{
    net::TcpListener,
    sync::{
        broadcast::{self, Sender},
        mpsc::{self, UnboundedSender},
    },
};

use g1_base::sync::MutexExt;
use g1_tokio::task::JoinGuard;

use bittorrent_base::{InfoHash, PeerId};
use bittorrent_peer::{Peer, Recvs};
use bittorrent_utp::UtpSocket;

use crate::{
    actor::{Actor, Peers},
    net::Listener,
    Endpoint, Update,
};

#[derive(Clone, Debug)]
pub struct Manager {
    connect_send: UnboundedSender<(Endpoint, Option<PeerId>)>,
    peers: Arc<Mutex<Peers>>,
    update_send: Sender<(Endpoint, Update)>,
}

pub type ManagerGuard = JoinGuard<Result<(), Error>>;

impl Manager {
    pub fn spawn(
        info_hash: InfoHash,
        tcp_listener_ipv4: Option<TcpListener>,
        tcp_listener_ipv6: Option<TcpListener>,
        utp_socket_ipv4: Option<&UtpSocket>,
        utp_socket_ipv6: Option<&UtpSocket>,
    ) -> (Self, Recvs, ManagerGuard) {
        tracing::info!(self_id = ?bittorrent_base::self_id());

        let (connect_send, connect_recv) = mpsc::unbounded_channel();

        let listener = Listener::new(
            info_hash.clone(),
            tcp_listener_ipv4,
            tcp_listener_ipv6,
            utp_socket_ipv4.map(UtpSocket::listener),
            utp_socket_ipv6.map(UtpSocket::listener),
        );

        let (recvs, sends) = bittorrent_peer::new_channels();

        let peers = Arc::new(Mutex::new(Peers::new(
            info_hash,
            utp_socket_ipv4.map(UtpSocket::connector),
            utp_socket_ipv6.map(UtpSocket::connector),
            sends,
        )));

        let update_capacity = *crate::update_queue_size();
        let (update_send, _) = broadcast::channel(update_capacity);

        (
            Self {
                connect_send,
                peers: peers.clone(),
                update_send: update_send.clone(),
            },
            recvs,
            JoinGuard::spawn(move |cancel| {
                Actor::new(
                    cancel,
                    connect_recv,
                    listener,
                    peers,
                    update_send,
                    update_capacity,
                )
                .run()
            }),
        )
    }

    pub fn connect(&self, peer_endpoint: Endpoint, peer_id: Option<PeerId>) {
        let _ = self.connect_send.send((peer_endpoint, peer_id));
    }

    pub fn peer_endpoints(&self) -> Vec<Endpoint> {
        self.peers.must_lock().peer_endpoints()
    }

    pub fn peers(&self) -> Vec<Peer> {
        self.peers.must_lock().peers()
    }

    pub fn get(&self, peer_endpoint: Endpoint) -> Option<Peer> {
        self.peers.must_lock().get(peer_endpoint)
    }

    pub fn subscribe(&self) -> broadcast::Receiver<(Endpoint, Update)> {
        self.update_send.subscribe()
    }
}
