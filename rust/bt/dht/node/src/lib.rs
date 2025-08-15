#![feature(duration_constructors_lite)]

mod insert;
mod lookup;
mod refresh;
mod route;
mod table;
mod token;

use std::io::Error;
use std::net::SocketAddr;
use std::sync::Arc;

use tokio::time::Instant;

use g1_tokio::task::{self, BoxJoinable, Joinable};

use bt_base::{InfoHash, NodeId};
use bt_dht_lookup::LookupPeers;
use bt_dht_proto::{NodeInfo, Token};
use bt_dht_reqrep::ReqRep;
use bt_peer::Peers;
use bt_udp::{Sink, Stream};

use crate::insert::Insert;
use crate::lookup::Lookup;
use crate::table::Table;
use crate::token::Issuer;

#[derive(Clone, Debug)]
pub struct Node {
    self_id: NodeId,
    reqrep: ReqRep,
    lookup: Lookup,
    insert: Insert,
}

pub type NodeGuard = BoxJoinable<Result<(), Error>>;

impl Node {
    pub fn spawn<I, O>(
        self_id: NodeId,
        peers: Peers,
        bootstrap: Arc<[String]>,
        stream: I,
        sink: O,
    ) -> (Self, NodeGuard)
    where
        I: Stream,
        O: Sink,
    {
        let table = Arc::new(Table::new(self_id.clone()));

        let (reqrep, reqrep_guard) = ReqRep::spawn(self_id.clone(), stream, sink);

        let lookup = Lookup::new(self_id.clone(), table.clone(), bootstrap, reqrep.clone());

        let insert = Insert::new(table.clone(), reqrep.clone());

        let (issuer, issuer_guard) = Issuer::spawn();

        let router_guard = route::spawn(table.clone(), reqrep.clone(), peers, issuer);

        let refresher_guard =
            refresh::spawn(self_id.clone(), table, lookup.clone(), insert.clone());

        (
            Self {
                self_id,
                reqrep,
                lookup,
                insert,
            },
            task::try_join([
                reqrep_guard.boxed(),
                issuer_guard.map(Ok).boxed(),
                router_guard.map(Ok).boxed(),
                refresher_guard.map(Ok).boxed(),
            ])
            .boxed(),
        )
    }

    pub async fn bootstrap(&self) -> bool {
        let Some(lookup_nodes) = self.lookup.lookup_nodes(self.self_id.clone()).await else {
            tracing::warn!("bootstrap routing table: lookup_nodes no result");
            return false;
        };
        for (node, last_ok) in lookup_nodes {
            self.insert.insert(node, last_ok).await;
        }
        tracing::info!("bootstrapped");
        true
    }

    pub async fn ping(&self, node_endpoint: SocketAddr) -> Option<NodeId> {
        self.reqrep
            .ping_raw(node_endpoint)
            .await
            .inspect_err(|error| tracing::warn!(%node_endpoint, %error, "ping"))
            .ok()
    }

    pub async fn insert_node(&self, node: NodeInfo, last_ok: Option<Instant>) {
        self.insert.insert(node, last_ok).await
    }

    pub async fn lookup_peers(&self, info_hash: InfoHash) -> Option<LookupPeers> {
        let (lookup_nodes, lookup_peers) = self.lookup.lookup_peers(info_hash).await?;
        for (node, last_ok) in lookup_nodes {
            self.insert.insert(node, last_ok).await;
        }
        (!lookup_peers.0.is_empty()).then_some(lookup_peers)
    }

    pub async fn announce_self(
        &self,
        node: NodeInfo,
        implied_port: bool,
        info_hash: InfoHash,
        port: u16,
        token: Token,
    ) -> bool {
        match self
            .reqrep
            .announce_peer(
                node.clone(),
                implied_port.then_some(true),
                info_hash.clone(),
                port,
                token.clone(),
            )
            .await
        {
            Ok(()) => {
                tracing::info!(?node, %info_hash, "announce_self");
                true
            }
            Err(error) => {
                tracing::warn!(?node, %info_hash, ?token, %error, "announce_self");
                false
            }
        }
    }
}
