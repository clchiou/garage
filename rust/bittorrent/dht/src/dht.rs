use std::io::Error;
use std::net::SocketAddr;
use std::sync::Arc;

use bytes::Bytes;
use futures::{sink::Sink, stream::Stream};

use g1_tokio::task::JoinArray;

use bittorrent_base::InfoHash;

use crate::{
    NodeId,
    agent::Agent,
    lookup::{Lookup, LookupPeers},
    reqrep::{self, GetPeers, Nodes},
};

#[derive(Clone, Debug)]
pub struct Dht {
    self_endpoint: SocketAddr,
    agent: Arc<Agent>,
}

pub type DhtGuard = JoinArray<Result<(), Error>, 2>;

impl Dht {
    pub fn spawn<Incoming, Outgoing>(
        self_endpoint: SocketAddr,
        incoming: Incoming,
        outgoing: Outgoing,
    ) -> (Self, DhtGuard)
    where
        Incoming: Stream<Item = Result<(SocketAddr, Bytes), Error>> + Send + Unpin + 'static,
        Outgoing: Sink<(SocketAddr, Bytes), Error = Error> + Send + Unpin + 'static,
    {
        let (reqrep, reqrep_guard) = reqrep::spawn(incoming, outgoing);
        let (agent, agent_guard) = Agent::spawn(crate::self_id().clone(), reqrep);
        (
            Self {
                self_endpoint,
                agent,
            },
            DhtGuard::new([reqrep_guard, agent_guard]),
        )
    }

    pub fn self_id(&self) -> NodeId {
        self.agent.self_id.clone()
    }

    pub fn self_endpoint(&self) -> SocketAddr {
        self.self_endpoint
    }

    pub async fn ping(&self, peer_endpoint: SocketAddr) -> Result<(), Error> {
        self.agent.connect(peer_endpoint).ping().await
    }

    pub async fn find_node(
        &self,
        peer_endpoint: SocketAddr,
        target: &[u8],
    ) -> Result<Nodes, Error> {
        self.agent.connect(peer_endpoint).find_node(target).await
    }

    pub async fn get_peers(
        &self,
        peer_endpoint: SocketAddr,
        info_hash: &[u8],
    ) -> Result<GetPeers, Error> {
        self.agent.connect(peer_endpoint).get_peers(info_hash).await
    }

    pub async fn announce_peer(
        &self,
        peer_endpoint: SocketAddr,
        info_hash: &[u8],
        port: u16,
        implied_port: Option<bool>,
        token: &[u8],
    ) -> Result<(), Error> {
        self.agent
            .connect(peer_endpoint)
            .announce_peer(info_hash, port, implied_port, token)
            .await
    }

    pub async fn lookup_nodes(&self, id: NodeId) -> Nodes {
        Lookup::new(self.agent.clone()).lookup_nodes(id).await
    }

    pub async fn lookup_peers(&self, info_hash: InfoHash) -> LookupPeers {
        Lookup::new(self.agent.clone())
            .lookup_peers(info_hash)
            .await
    }
}
