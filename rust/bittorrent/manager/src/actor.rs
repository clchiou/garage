use std::collections::{hash_map::Entry, HashMap};
use std::io::Error;
use std::sync::{Arc, Mutex};

use tokio::sync::{broadcast::Sender, mpsc::UnboundedReceiver};

use g1_base::{
    fmt::{DebugExt, InsertPlaceholder},
    future::ReadyQueue,
    sync::MutexExt,
};

use bittorrent_base::{InfoHash, PeerId};
use bittorrent_peer::{Agent, Sends};
use bittorrent_utp::UtpSocket;

use crate::{
    net::{Acceptor, Connector},
    Endpoint, Preference, Socket, Update,
};

#[derive(DebugExt)]
pub(crate) struct Actor {
    peers: Arc<Mutex<Peers>>,

    connect_recv: UnboundedReceiver<(Endpoint, Option<PeerId>)>,
    acceptor: Acceptor,
    #[debug(with = InsertPlaceholder)]
    joins: ReadyQueue<Endpoint>,

    update_send: Sender<(Endpoint, Update)>,
    update_capacity: usize,
}

#[derive(Debug)]
pub(crate) struct Peers {
    info_hash: InfoHash,
    utp_socket_v4: Option<Arc<UtpSocket>>,
    utp_socket_v6: Option<Arc<UtpSocket>>,
    sends: Sends,

    // We do not evict `Connector` entries.  Consequently, `Manager::peer_endpoints` will return
    // all peer endpoints that we have ever encountered.
    connectors: HashMap<Endpoint, Option<Connector>>,

    agents: HashMap<Endpoint, Arc<Agent>>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ConnectorInUse;

impl Actor {
    pub(crate) fn new(
        peers: Arc<Mutex<Peers>>,
        connect_recv: UnboundedReceiver<(Endpoint, Option<PeerId>)>,
        acceptor: Acceptor,
        joins: ReadyQueue<Endpoint>,
        update_send: Sender<(Endpoint, Update)>,
        update_capacity: usize,
    ) -> Self {
        Self {
            peers,
            connect_recv,
            acceptor,
            joins,
            update_send,
            update_capacity,
        }
    }

    pub(crate) async fn run(mut self) -> Result<(), Error> {
        loop {
            tokio::select! {
                peer_endpoint = self.connect_recv.recv() => {
                    match peer_endpoint {
                        Some((peer_endpoint, peer_id)) => {
                            self.handle_connect(peer_endpoint, peer_id).await;
                        }
                        None => break,
                    }
                }
                accept = self.acceptor.accept() => {
                    let (socket, peer_endpoint, prefs) = accept?;
                    self.handle_accept(socket, peer_endpoint, prefs).await;
                }
                peer_endpoint = self.joins.pop_ready() => {
                    match peer_endpoint {
                        Some(peer_endpoint) => self.handle_join(peer_endpoint).await,
                        None => break,
                    }
                }
            }
        }

        let agents = self.peers.must_lock().take_agents();
        for (peer_endpoint, agent) in agents {
            self.shutdown_agent(peer_endpoint, agent).await;
        }

        Ok(())
    }

    async fn handle_connect(&self, peer_endpoint: Endpoint, peer_id: Option<PeerId>) {
        let mut connector = {
            let mut peers = self.peers.must_lock();
            if peers.contains_agent(peer_endpoint) {
                tracing::debug!(?peer_endpoint, "peer agent is still running");
                return;
            }
            match peers.take_connector(peer_endpoint) {
                Ok(connector) => connector,
                Err(ConnectorInUse) => {
                    tracing::error!(?peer_endpoint, "already connecting to peer");
                    return;
                }
            }
        };
        if peer_id.is_some() {
            connector.set_peer_id(peer_id);
        }

        // For now, we call `connect` here, rather than in a separate task, for the sake of
        // simplicity.
        let socket = connector.connect().await;

        let agent = {
            let mut peers = self.peers.must_lock();
            peers.return_connector(peer_endpoint, connector);
            match socket {
                Ok(socket) => peers.insert_agent(peer_endpoint, socket),
                Err(error) => {
                    // Log it at debug level since its cause has already been logged by `connect`.
                    tracing::debug!(?peer_endpoint, ?error, "peer socket connect error");
                    return;
                }
            }
        };
        self.handle_insert_agent(peer_endpoint, agent).await;
    }

    async fn handle_accept(&self, socket: Socket, peer_endpoint: Endpoint, prefs: Vec<Preference>) {
        let agent = {
            let mut peers = self.peers.must_lock();
            match peers.upsert_connector(peer_endpoint, socket.peer_id(), prefs) {
                Ok(()) => peers.insert_agent(peer_endpoint, socket),
                Err(ConnectorInUse) => Err(socket),
            }
        };
        self.handle_insert_agent(peer_endpoint, agent).await;
    }

    async fn handle_insert_agent(
        &self,
        peer_endpoint: Endpoint,
        agent: Result<Arc<Agent>, Socket>,
    ) {
        match agent {
            Ok(agent) => {
                self.send_update(peer_endpoint, Update::Start);
                let _ = self.joins.push(async move {
                    agent.join().await;
                    peer_endpoint
                });
            }
            Err(mut socket) => {
                tracing::error!(?peer_endpoint, "conflict with running peer agent");
                if let Err(error) = socket.shutdown().await {
                    tracing::warn!(?peer_endpoint, ?error, "peer socket shutdown error");
                }
            }
        }
    }

    async fn handle_join(&self, peer_endpoint: Endpoint) {
        let agent = self.peers.must_lock().remove_agent(peer_endpoint);
        if let Some(agent) = agent {
            self.shutdown_agent(peer_endpoint, agent).await;
        }
    }

    async fn shutdown_agent(&self, peer_endpoint: Endpoint, agent: Arc<Agent>) {
        if let Err(error) = agent.shutdown().await {
            tracing::warn!(?peer_endpoint, ?error, "peer agent error");
        }
        self.send_update(peer_endpoint, Update::Stop);
    }

    fn send_update(&self, peer_endpoint: Endpoint, update: Update) {
        let num_updates_queued = self.update_send.len();
        if num_updates_queued * 10 >= self.update_capacity * 9 {
            tracing::warn!(num_updates_queued, "update queue is almost full");
        }
        let _ = self.update_send.send((peer_endpoint, update));
    }
}

impl Peers {
    pub(crate) fn new(
        info_hash: InfoHash,
        utp_socket_v4: Option<Arc<UtpSocket>>,
        utp_socket_v6: Option<Arc<UtpSocket>>,
        sends: Sends,
    ) -> Self {
        Self {
            info_hash,
            utp_socket_v4,
            utp_socket_v6,
            sends,
            connectors: HashMap::new(),
            agents: HashMap::new(),
        }
    }

    pub(crate) fn peer_endpoints(&self) -> Vec<Endpoint> {
        let mut peer_endpoints: Vec<_> = self.connectors.keys().cloned().collect();
        // It seems like a good idea to return the peer endpoints in a fixed order.
        peer_endpoints.sort();
        peer_endpoints
    }

    fn take_connector(&mut self, peer_endpoint: Endpoint) -> Result<Connector, ConnectorInUse> {
        match self.connectors.entry(peer_endpoint) {
            Entry::Occupied(entry) => entry.into_mut().take().ok_or(ConnectorInUse),
            Entry::Vacant(entry) => {
                let _ = entry.insert(None);
                Ok(Connector::new_default(
                    self.info_hash.clone(),
                    None,
                    peer_endpoint,
                    None,
                    self.utp_socket_v4.clone(),
                    self.utp_socket_v6.clone(),
                ))
            }
        }
    }

    fn return_connector(&mut self, peer_endpoint: Endpoint, connector: Connector) {
        match self.connectors.get_mut(&peer_endpoint) {
            Some(entry) => match entry {
                None => {
                    *entry = Some(connector);
                }
                Some(_) => std::panic!("peer connector entry was returned: {:?}", peer_endpoint),
            },
            None => std::panic!("peer connector entry does not exist: {:?}", peer_endpoint),
        }
    }

    fn upsert_connector(
        &mut self,
        peer_endpoint: Endpoint,
        peer_id: PeerId,
        prefs: Vec<Preference>,
    ) -> Result<(), ConnectorInUse> {
        match self.connectors.entry(peer_endpoint) {
            Entry::Occupied(entry) => match entry.into_mut() {
                Some(connector) => {
                    connector.set_peer_id(Some(peer_id));
                    connector.set_preferences(prefs);
                    Ok(())
                }
                None => Err(ConnectorInUse),
            },
            Entry::Vacant(entry) => {
                let _ = entry.insert(Some(Connector::new_default(
                    self.info_hash.clone(),
                    Some(peer_id),
                    peer_endpoint,
                    Some(prefs),
                    self.utp_socket_v4.clone(),
                    self.utp_socket_v6.clone(),
                )));
                Ok(())
            }
        }
    }

    pub(crate) fn agents(&self) -> Vec<Arc<Agent>> {
        let mut agents: Vec<_> = self.agents.values().cloned().collect();
        // It seems like a good idea to return the agents in a fixed order.
        agents.sort_by_key(|agent| agent.peer_endpoint());
        agents
    }

    fn contains_agent(&self, peer_endpoint: Endpoint) -> bool {
        self.agents.contains_key(&peer_endpoint)
    }

    pub(crate) fn get_agent(&self, peer_endpoint: Endpoint) -> Option<Arc<Agent>> {
        self.agents.get(&peer_endpoint).cloned()
    }

    fn insert_agent(
        &mut self,
        peer_endpoint: Endpoint,
        socket: Socket,
    ) -> Result<Arc<Agent>, Socket> {
        match self.agents.entry(peer_endpoint) {
            Entry::Occupied(_) => Err(socket),
            Entry::Vacant(entry) => Ok(entry
                .insert(Arc::new(Agent::new(
                    socket,
                    peer_endpoint,
                    self.sends.clone(),
                )))
                .clone()),
        }
    }

    fn remove_agent(&mut self, peer_endpoint: Endpoint) -> Option<Arc<Agent>> {
        self.agents.remove(&peer_endpoint)
    }

    fn take_agents(&mut self) -> Vec<(Endpoint, Arc<Agent>)> {
        self.agents.drain().collect()
    }
}
