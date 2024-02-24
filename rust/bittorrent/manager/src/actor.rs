use std::collections::{btree_map::Entry, BTreeMap, HashMap};
use std::io::Error;
use std::sync::{Arc, Mutex};

use tokio::sync::{broadcast::Sender, mpsc::UnboundedReceiver};
use tokio::task::Id;

use g1_base::sync::MutexExt;
use g1_tokio::task::{Cancel, JoinQueue};

use bittorrent_base::{InfoHash, PeerId};
use bittorrent_peer::{Peer, PeerGuard, Sends};
use bittorrent_utp::UtpConnector;

use crate::{
    net::{Connector, Listener},
    Endpoint, Preference, Socket, Update,
};

#[derive(Debug)]
pub(crate) struct Actor {
    cancel: Cancel,

    connect_recv: UnboundedReceiver<(Endpoint, Option<PeerId>)>,
    listener: Listener,

    peers: Arc<Mutex<Peers>>,
    tasks: JoinQueue<Result<(), Error>>,

    update_send: Sender<(Endpoint, Update)>,
    update_capacity: usize,
}

#[derive(Debug)]
pub(crate) struct Peers {
    info_hash: InfoHash,
    utp_connector_ipv4: Option<UtpConnector>,
    utp_connector_ipv6: Option<UtpConnector>,
    sends: Sends,

    // We do not evict `Connector` entries.  Consequently, `Manager::peer_endpoints` will return
    // all peer endpoints that we have ever encountered.
    //
    // Use `BTreeMap` because it seems like a good idea to return the peer endpoints in a fixed
    // order.
    connectors: BTreeMap<Endpoint, Option<Connector>>,

    // Use `BTreeMap` for the same reason above.
    peers: BTreeMap<Endpoint, Peer>,
    // Only for `remove_by_id`.
    peer_endpoints: HashMap<Id, Endpoint>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ConnectorInUse;

impl Actor {
    pub(crate) fn new(
        cancel: Cancel,
        connect_recv: UnboundedReceiver<(Endpoint, Option<PeerId>)>,
        listener: Listener,
        peers: Arc<Mutex<Peers>>,
        update_send: Sender<(Endpoint, Update)>,
        update_capacity: usize,
    ) -> Self {
        Self {
            cancel: cancel.clone(),
            connect_recv,
            listener,
            peers,
            tasks: JoinQueue::with_cancel(cancel),
            update_send,
            update_capacity,
        }
    }

    pub(crate) async fn run(mut self) -> Result<(), Error> {
        loop {
            tokio::select! {
                _ = self.cancel.wait() => break,

                peer_endpoint = self.connect_recv.recv() => {
                    let Some((peer_endpoint, peer_id)) = peer_endpoint else { break };
                    self.handle_connect(peer_endpoint, peer_id).await;
                }
                accept = self.listener.accept() => {
                    let (socket, peer_endpoint, prefs) = accept?;
                    self.handle_accept(socket, peer_endpoint, prefs).await;
                }

                guard = self.tasks.join_next() => {
                    let Some(guard) = guard else { break };
                    self.handle_peer_stop(guard);
                }
            }
        }

        self.tasks.cancel();
        while let Some(guard) = self.tasks.join_next().await {
            self.handle_peer_stop(guard);
        }

        Ok(())
    }

    async fn handle_connect(&self, peer_endpoint: Endpoint, peer_id: Option<PeerId>) {
        let mut connector = {
            let mut peers = self.peers.must_lock();
            if peers.contains(peer_endpoint) {
                tracing::debug!(?peer_endpoint, "peer is currently running");
                return;
            }
            match peers.borrow_connector(peer_endpoint) {
                Ok(connector) => connector,
                Err(ConnectorInUse) => {
                    tracing::error!(?peer_endpoint, "we are currently connecting to peer");
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

        let guard = {
            let mut peers = self.peers.must_lock();
            peers.return_connector(peer_endpoint, connector);
            match socket {
                Ok(socket) => peers.spawn(peer_endpoint, socket),
                Err(error) => {
                    // Log it at debug level since its cause has already been logged by `connect`.
                    tracing::debug!(?peer_endpoint, ?error, "peer socket connect error");
                    return;
                }
            }
        };
        self.handle_peer_start(peer_endpoint, guard).await;
    }

    async fn handle_accept(&self, socket: Socket, peer_endpoint: Endpoint, prefs: Vec<Preference>) {
        let guard = {
            let mut peers = self.peers.must_lock();
            match peers.update_connector(peer_endpoint, socket.peer_id(), prefs) {
                Ok(()) => peers.spawn(peer_endpoint, socket),
                Err(ConnectorInUse) => Err(socket),
            }
        };
        self.handle_peer_start(peer_endpoint, guard).await;
    }

    async fn handle_peer_start(&self, peer_endpoint: Endpoint, guard: Result<PeerGuard, Socket>) {
        match guard {
            Ok(guard) => match self.tasks.push(guard) {
                Ok(()) => self.send_update(peer_endpoint, Update::Start),
                Err(guard) => {
                    self.peers.must_lock().remove_by_id(guard.id());
                }
            },
            Err(mut socket) => {
                tracing::error!(?peer_endpoint, "new socket conflicts with current peer");
                if let Err(error) = socket.shutdown().await {
                    tracing::warn!(?peer_endpoint, ?error, "peer socket shutdown error");
                }
            }
        }
    }

    fn handle_peer_stop(&self, mut guard: PeerGuard) {
        let peer_endpoint = self.peers.must_lock().remove_by_id(guard.id());
        self.send_update(peer_endpoint, Update::Stop);
        match guard.take_result() {
            Ok(Ok(())) => {}
            Ok(Err(error)) => tracing::warn!(?peer_endpoint, ?error, "peer error"),
            Err(error) => tracing::warn!(?peer_endpoint, ?error, "peer task error"),
        }
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
        utp_connector_ipv4: Option<UtpConnector>,
        utp_connector_ipv6: Option<UtpConnector>,
        sends: Sends,
    ) -> Self {
        Self {
            info_hash,
            utp_connector_ipv4,
            utp_connector_ipv6,
            sends,
            connectors: BTreeMap::new(),
            peers: BTreeMap::new(),
            peer_endpoints: HashMap::new(),
        }
    }

    pub(crate) fn peer_endpoints(&self) -> Vec<Endpoint> {
        self.connectors.keys().cloned().collect()
    }

    fn borrow_connector(&mut self, peer_endpoint: Endpoint) -> Result<Connector, ConnectorInUse> {
        match self.connectors.entry(peer_endpoint) {
            Entry::Occupied(entry) => entry.into_mut().take().ok_or(ConnectorInUse),
            Entry::Vacant(entry) => {
                let _ = entry.insert(None);
                Ok(Connector::new(
                    self.info_hash.clone(),
                    None,
                    peer_endpoint,
                    None,
                    self.utp_connector_ipv4.clone(),
                    self.utp_connector_ipv6.clone(),
                ))
            }
        }
    }

    fn return_connector(&mut self, peer_endpoint: Endpoint, connector: Connector) {
        match self.connectors.get_mut(&peer_endpoint) {
            Some(entry) => match entry {
                None => *entry = Some(connector),
                Some(_) => std::panic!("peer connector entry was returned: {:?}", peer_endpoint),
            },
            None => std::panic!("peer connector entry does not exist: {:?}", peer_endpoint),
        }
    }

    fn update_connector(
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
                let _ = entry.insert(Some(Connector::new(
                    self.info_hash.clone(),
                    Some(peer_id),
                    peer_endpoint,
                    Some(prefs),
                    self.utp_connector_ipv4.clone(),
                    self.utp_connector_ipv6.clone(),
                )));
                Ok(())
            }
        }
    }

    pub(crate) fn peers(&self) -> Vec<Peer> {
        self.peers.values().cloned().collect()
    }

    fn contains(&self, peer_endpoint: Endpoint) -> bool {
        self.peers.contains_key(&peer_endpoint)
    }

    pub(crate) fn get(&self, peer_endpoint: Endpoint) -> Option<Peer> {
        self.peers.get(&peer_endpoint).cloned()
    }

    fn spawn(&mut self, peer_endpoint: Endpoint, socket: Socket) -> Result<PeerGuard, Socket> {
        match self.peers.entry(peer_endpoint) {
            Entry::Occupied(_) => Err(socket),
            Entry::Vacant(entry) => {
                let (peer, guard) = Peer::spawn(socket, peer_endpoint, self.sends.clone());
                assert!(self
                    .peer_endpoints
                    .insert(guard.id(), peer_endpoint)
                    .is_none());
                entry.insert(peer);
                Ok(guard)
            }
        }
    }

    fn remove_by_id(&mut self, id: Id) -> Endpoint {
        let peer_endpoint = self.peer_endpoints.remove(&id).unwrap();
        self.peers.remove(&peer_endpoint).unwrap();
        peer_endpoint
    }
}
