use std::io::Error;
use std::sync::{Arc, Mutex};

use tokio::{
    net::TcpListener,
    sync::{
        broadcast::{self, Sender},
        mpsc::{self, UnboundedSender},
        Mutex as AsyncMutex,
    },
    task::JoinHandle,
};

use g1_base::{
    fmt::{DebugExt, InsertPlaceholder},
    future::ReadyQueue,
    sync::MutexExt,
};
use g1_tokio::task::{self, JoinTaskError};

use bittorrent_base::{InfoHash, PeerId};
use bittorrent_peer::{Agent, Recvs};
use bittorrent_utp::UtpSocket;

use crate::{
    actor::{Actor, Peers},
    error,
    net::Acceptor,
    Endpoint, Update,
};

#[derive(DebugExt)]
pub struct Manager {
    peers: Arc<Mutex<Peers>>,

    connect_send: UnboundedSender<(Endpoint, Option<PeerId>)>,
    #[debug(with = InsertPlaceholder)]
    joins: ReadyQueue<Endpoint>,

    update_send: Sender<(Endpoint, Update)>,

    task: AsyncMutex<JoinHandle<Result<(), Error>>>,
}

impl Manager {
    pub fn new(
        info_hash: InfoHash,
        tcp_listener_v4: Option<TcpListener>,
        tcp_listener_v6: Option<TcpListener>,
        utp_socket_v4: Option<Arc<UtpSocket>>,
        utp_socket_v6: Option<Arc<UtpSocket>>,
    ) -> (Self, Recvs) {
        let (recvs, sends) = bittorrent_peer::new_channels();

        let peers = Arc::new(Mutex::new(Peers::new(
            info_hash.clone(),
            utp_socket_v4.clone(),
            utp_socket_v6.clone(),
            sends,
        )));

        let (connect_send, connect_recv) = mpsc::unbounded_channel();

        let acceptor = Acceptor::new_default(
            info_hash,
            tcp_listener_v4,
            tcp_listener_v6,
            utp_socket_v4,
            utp_socket_v6,
        );

        let joins = ReadyQueue::new();

        let update_capacity = *crate::update_queue_size();
        let (update_send, _) = broadcast::channel(update_capacity);

        let actor = Actor::new(
            peers.clone(),
            connect_recv,
            acceptor,
            joins.clone(), // `ReadyQueue::clone` is shallow.
            update_send.clone(),
            update_capacity,
        );

        (
            Self {
                peers,
                connect_send,
                joins,
                update_send,
                task: AsyncMutex::new(tokio::spawn(actor.run())),
            },
            recvs,
        )
    }

    pub fn peer_endpoints(&self) -> Vec<Endpoint> {
        self.peers.must_lock().peer_endpoints()
    }

    pub fn connect(&self, peer_endpoint: Endpoint, peer_id: Option<PeerId>) {
        let _ = self.connect_send.send((peer_endpoint, peer_id));
    }

    pub fn agents(&self) -> Vec<Arc<Agent>> {
        self.peers.must_lock().agents()
    }

    pub fn get(&self, peer_endpoint: Endpoint) -> Option<Arc<Agent>> {
        self.peers.must_lock().get_agent(peer_endpoint)
    }

    pub fn subscribe(&self) -> broadcast::Receiver<(Endpoint, Update)> {
        self.update_send.subscribe()
    }

    pub fn close(&self) {
        self.joins.close();
    }

    pub async fn shutdown(&self) -> Result<(), Error> {
        self.close();
        task::join_task(&self.task, *crate::grace_period())
            .await
            .map_err(|error| match error {
                JoinTaskError::Cancelled => error::Error::Cancelled,
                JoinTaskError::Timeout => error::Error::ShutdownGracePeriodExceeded,
            })?
    }
}

impl Drop for Manager {
    fn drop(&mut self) {
        self.task.get_mut().abort();
    }
}
