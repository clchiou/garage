use std::collections::HashSet;

use g1_base::iter::IteratorExt;

use bt_base::{InfoHash, NodeId};
use bt_dht_proto::{
    FindNodeResponse, GetPeersResponse, Message, NodeInfo, PeerInfo, Query, Response, Token,
};

pub trait Target {
    type Acc: Acc<Output = Self::Output>;
    type Output;

    fn to_id(&self) -> NodeId;

    fn new_query(&self, self_id: NodeId) -> Message;
}

pub trait Acc {
    type Output;

    fn new() -> Self;

    // TODO: Should we fix `result_large_err`?
    #[allow(clippy::result_large_err)]
    fn update<T>(
        &mut self,
        target: &T,
        info: NodeInfo,
        response: Response,
    ) -> Result<Vec<NodeInfo>, Response>
    where
        T: Target<Acc = Self>;

    fn finish(self) -> Self::Output;
}

#[derive(Debug)]
pub struct LookupNodesAcc;

#[derive(Debug)]
pub struct LookupPeersAcc {
    peers: HashSet<PeerInfo>,
    closest: Option<(NodeInfo, Token)>,
}

pub type LookupPeers = (
    Vec<PeerInfo>,
    // Closest node to which we can send `announce_peer`.
    // TODO: Should we return multiple closest nodes?
    Option<(NodeInfo, Token)>,
);

impl Target for NodeId {
    type Acc = LookupNodesAcc;
    type Output = ();

    fn to_id(&self) -> NodeId {
        self.clone()
    }

    fn new_query(&self, self_id: NodeId) -> Message {
        Query::find_node(self_id, self.clone())
    }
}

impl Acc for LookupNodesAcc {
    type Output = ();

    fn new() -> Self {
        Self
    }

    fn update<T>(
        &mut self,
        _target: &T,
        _info: NodeInfo,
        response: Response,
    ) -> Result<Vec<NodeInfo>, Response>
    where
        T: Target<Acc = Self>,
    {
        response
            .try_into()
            .map(|FindNodeResponse { nodes, .. }| nodes)
    }

    fn finish(self) -> Self::Output {}
}

impl Target for InfoHash {
    type Acc = LookupPeersAcc;
    type Output = LookupPeers;

    fn to_id(&self) -> NodeId {
        NodeId::pretend(self.clone())
    }

    fn new_query(&self, self_id: NodeId) -> Message {
        Query::get_peers(self_id, self.clone())
    }
}

impl Acc for LookupPeersAcc {
    type Output = LookupPeers;

    fn new() -> Self {
        Self {
            peers: HashSet::new(),
            closest: None,
        }
    }

    fn update<T>(
        &mut self,
        target: &T,
        info: NodeInfo,
        response: Response,
    ) -> Result<Vec<NodeInfo>, Response>
    where
        T: Target<Acc = Self>,
    {
        let GetPeersResponse {
            token,
            values,
            nodes,
            ..
        } = response.into();

        if let Some(peers) = values {
            self.peers.extend(peers);
        }

        if let Some(token) = token {
            if self.closest.as_ref().is_none_or(|(closest, _)| {
                let t = target.to_id();
                info.id.distance(&t) < closest.id.distance(&t)
            }) {
                self.closest = Some((info, token));
            }
        }

        Ok(nodes.unwrap_or_default())
    }

    fn finish(self) -> Self::Output {
        let Self { peers, closest } = self;
        (peers.into_iter().collect_then_sort(), closest)
    }
}
