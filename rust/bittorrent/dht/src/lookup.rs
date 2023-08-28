//! Kademlia Node Lookup Algorithm
// TODO: To be honest, I am not sure whether our implementation complies with BEP 5 because its
// wording is a bit ambiguous to me.  How can we ensure compliance with BEP 5?

use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::io::Error;
use std::mem;
use std::net::SocketAddr;
use std::sync::Arc;

use async_trait::async_trait;
use bitvec::prelude::*;

use g1_base::sync::MutexExt;
use g1_tokio::{net, task::Joiner};

use bittorrent_base::InfoHash;

use crate::{
    reqrep::{Client, GetPeers, Nodes, Token},
    server::Inner,
    Distance, NodeContactInfo, NodeId, NodeIdBitSlice,
};

#[derive(Debug)]
pub(crate) struct Lookup {
    inner: Arc<Inner>,
    limit: usize,
    concurrency: usize,
}

pub(crate) type LookupPeers = (
    Peers,
    // Closest node to which we may send `announce_peer`.
    Option<(NodeContactInfo, Token)>,
);

type Peers = BTreeSet<SocketAddr>;

impl Lookup {
    pub(crate) fn new(inner: Arc<Inner>) -> Self {
        Self::with_limit(inner, *crate::k(), *crate::alpha())
    }

    fn with_limit(inner: Arc<Inner>, limit: usize, concurrency: usize) -> Self {
        Self {
            inner,
            limit,
            concurrency,
        }
    }

    pub(crate) async fn lookup_nodes(&self, id: NodeId) -> Nodes {
        self.lookup(NodeLookuper, id).await
    }

    pub(crate) async fn lookup_peers(&self, info_hash: InfoHash) -> LookupPeers {
        self.lookup(PeerLookuper::new(), info_hash).await
    }

    async fn lookup<L, I>(&self, mut lookuper: L, id: I) -> L::Output
    where
        L: Lookuper,
        I: AsRef<[u8]> + Bits + Clone + Send + Sync + 'static,
    {
        // Create a map from `Distance` to `NodeContactInfo`.  We may use `Distance` as the map key
        // because the XOR metric is unidirectional, which means that `p == q` if and only if
        // `d(id, p) == d(id, q)`.
        let mut candidates = BTreeMap::from_iter(into_entries(
            self.inner
                .routing
                .must_lock()
                .get_closest_with_limit(id.bits(), self.limit),
            id.bits(),
        ));
        if candidates.is_empty() {
            candidates = self.bootstrap(id.clone()).await;
        }

        let mut good_nodes = BTreeMap::new();
        let mut closest_nodes = Nodes::new();
        let mut have_been_queried = HashSet::new();
        while !candidates.is_empty() {
            let closest_candidates: Vec<_> = mem::take(&mut candidates)
                .values()
                .filter(|node| !have_been_queried.contains(*node))
                .take(self.limit)
                .cloned()
                .collect();

            have_been_queried.extend(closest_candidates.iter().cloned());
            let queries: Vec<_> = closest_candidates
                .into_iter()
                .map(|candidate| {
                    let inner = self.inner.clone();
                    let id = id.clone();
                    async move {
                        let client = inner.connect(candidate.endpoint);
                        (candidate, L::request(client, id.as_ref()).await)
                    }
                })
                .collect();

            let mut tasks = Joiner::new(queries, self.concurrency);
            while let Some(join_result) = tasks.join_next().await {
                // We can call `unwrap` because we do not expect tasks to crash.
                let (candidate, result) = join_result.unwrap();
                match result {
                    Ok(response) => {
                        let candidate_distance = Distance::measure(id.bits(), candidate.id.bits());
                        candidates.extend(into_entries(
                            lookuper.process_response(&candidate, &candidate_distance, response),
                            id.bits(),
                        ));
                        assert_eq!(good_nodes.insert(candidate_distance, candidate), None);
                    }
                    Err(error) => {
                        tracing::warn!(?candidate, ?error, "{} error", L::KRPC_METHOD_NAME);
                        let _ = self.inner.routing.must_lock().remove(&candidate);
                    }
                }
            }

            let next_closest_nodes = good_nodes.values().take(self.limit).cloned().collect();
            if closest_nodes == next_closest_nodes {
                break;
            } else {
                drop(mem::replace(&mut closest_nodes, next_closest_nodes));
            }
        }

        lookuper.finish(closest_nodes)
    }

    async fn bootstrap<I>(&self, id: I) -> BTreeMap<Distance, NodeContactInfo>
    where
        I: AsRef<[u8]> + Bits + Clone + Send + Sync + 'static,
    {
        let queries: Vec<_> = crate::bootstrap()
            .iter()
            .cloned()
            .map(|bootstrap| {
                let inner = self.inner.clone();
                let id = id.clone();
                async move {
                    let nodes: Result<Nodes, Error> = try {
                        let endpoint = net::lookup_host_first(&bootstrap).await?;
                        inner.connect(endpoint).find_node(id.as_ref()).await?
                    };
                    match nodes {
                        Ok(nodes) => nodes,
                        Err(error) => {
                            tracing::warn!(bootstrap, ?error, "bootstrap error");
                            Vec::new()
                        }
                    }
                }
            })
            .collect();

        let mut candidates = BTreeMap::new();
        let mut tasks = Joiner::new(queries, self.concurrency);
        while let Some(join_result) = tasks.join_next().await {
            // We can call `unwrap` because we do not expect tasks to crash.
            candidates.extend(into_entries(join_result.unwrap(), id.bits()));
        }
        candidates
    }
}

fn into_entries<'a, I>(
    nodes: I,
    id: &'a NodeIdBitSlice,
) -> impl Iterator<Item = (Distance, NodeContactInfo)> + 'a
where
    I: IntoIterator<Item = NodeContactInfo>,
    I::IntoIter: 'a,
{
    nodes
        .into_iter()
        .map(|node| (Distance::measure(id, node.id.bits()), node))
}

/// Abstracts away the details of `NodeId` and `InfoHash`.
// For now, we are not creating a separate `InfoHashBitSlice` type for the sake of convenience.
trait Bits {
    fn bits(&self) -> &NodeIdBitSlice;
}

impl Bits for NodeId {
    fn bits(&self) -> &NodeIdBitSlice {
        self.bits()
    }
}

impl Bits for InfoHash {
    fn bits(&self) -> &NodeIdBitSlice {
        self.as_ref().view_bits()
    }
}

/// Abstracts away the details of `lookup_nodes` and `lookup_peers`.
#[async_trait]
trait Lookuper {
    type Response: Send + Sync + 'static;
    type Output;

    const KRPC_METHOD_NAME: &'static str;

    async fn request(client: Client<'_>, id: &[u8]) -> Result<Self::Response, Error>;

    fn process_response(
        &mut self,
        node: &NodeContactInfo,
        node_distance: &Distance,
        response: Self::Response,
    ) -> Nodes;

    fn finish(self, nodes: Nodes) -> Self::Output;
}

#[derive(Debug)]
struct NodeLookuper;

#[derive(Debug)]
struct PeerLookuper {
    peers: Peers,
    closest: Option<(NodeContactInfo, Distance, Token)>,
}

#[async_trait]
impl Lookuper for NodeLookuper {
    type Response = Nodes;
    type Output = Nodes;

    const KRPC_METHOD_NAME: &'static str = "find_node";

    async fn request(client: Client<'_>, id: &[u8]) -> Result<Self::Response, Error> {
        client.find_node(id).await
    }

    fn process_response(
        &mut self,
        _node: &NodeContactInfo,
        _node_distance: &Distance,
        response: Self::Response,
    ) -> Nodes {
        response
    }

    fn finish(self, nodes: Nodes) -> Self::Output {
        nodes
    }
}

impl PeerLookuper {
    fn new() -> Self {
        Self {
            peers: BTreeSet::new(),
            closest: None,
        }
    }

    fn other_is_closer(&self, node_distance: &Distance) -> bool {
        match &self.closest {
            Some((_, distance, _)) => node_distance < distance,
            None => true,
        }
    }
}

#[async_trait]
impl Lookuper for PeerLookuper {
    type Response = GetPeers;
    type Output = LookupPeers;

    const KRPC_METHOD_NAME: &'static str = "get_peers";

    async fn request(client: Client<'_>, id: &[u8]) -> Result<Self::Response, Error> {
        client.get_peers(id).await
    }

    fn process_response(
        &mut self,
        node: &NodeContactInfo,
        node_distance: &Distance,
        response: Self::Response,
    ) -> Nodes {
        let (token, peers, nodes) = response;
        if let Some(peers) = peers {
            self.peers.extend(peers);
            if self.other_is_closer(node_distance) {
                tracing::debug!(?node, "find closer node");
                self.closest = Some((node.clone(), node_distance.clone(), token.unwrap()));
            }
        }
        nodes.unwrap_or_default()
    }

    fn finish(self, _nodes: Nodes) -> Self::Output {
        (
            self.peers,
            self.closest.map(|(closest, _, token)| (closest, token)),
        )
    }
}
