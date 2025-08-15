use std::collections::HashSet;
use std::sync::Arc;

use tokio::net;
use tokio::time::Instant;

use bt_base::{InfoHash, NodeId};
use bt_dht_lookup::{LookupPeers, Target};
use bt_dht_proto::NodeInfo;
use bt_dht_reqrep::ReqRep;

use crate::table::Table;

#[derive(Clone, Debug)]
pub(crate) struct Lookup {
    self_id: NodeId,
    table: Arc<Table>,
    bootstrap: Arc<[String]>,
    reqrep: ReqRep,
}

pub(crate) type LookupNodes = Vec<(NodeInfo, Option<Instant>)>;

impl Lookup {
    pub(crate) fn new(
        self_id: NodeId,
        table: Arc<Table>,
        bootstrap: Arc<[String]>,
        reqrep: ReqRep,
    ) -> Self {
        Self {
            self_id,
            table,
            bootstrap,
            reqrep,
        }
    }

    pub(crate) async fn lookup_nodes(&self, target: NodeId) -> Option<LookupNodes> {
        self.lookup(target)
            .await
            .and_then(|(lookup_nodes, ())| (!lookup_nodes.is_empty()).then_some(lookup_nodes))
    }

    pub(crate) async fn lookup_peers(
        &self,
        info_hash: InfoHash,
    ) -> Option<(LookupNodes, LookupPeers)> {
        self.lookup(info_hash).await
    }

    async fn lookup<T>(&self, target: T) -> Option<(LookupNodes, T::Output)>
    where
        T: Target,
    {
        let mut lookup = self.bootstrap(target).await?;
        let mut lookup_nodes = LookupNodes::new();

        while let Some(queries) = lookup.next_iteration() {
            for (node, query) in queries {
                let response = match self.reqrep.request(node.clone(), query).await {
                    Ok(response) => response,
                    Err(error) => {
                        // We do not distinguish between an error caused by the reqrep actor's exit
                        // and an actual error caused by the remote node.
                        tracing::warn!(?node, %error, "lookup");
                        self.table.write().update_err(node.id);
                        continue;
                    }
                };

                match lookup.update(node.clone(), response) {
                    Ok(()) => {
                        // This node responds to our query and is considered "good".  We will
                        // insert it into the routing table and update the table here in case the
                        // node is already present.
                        lookup_nodes.push((node.clone(), Some(Instant::now())));
                        self.table.write().update_ok(node);
                    }
                    Err(response) => {
                        tracing::warn!(?node, ?response, "lookup: invalid response");
                        self.table.write().update_err(node.id);
                    }
                }
            }
        }

        Some((lookup_nodes, lookup.finish()))
    }

    async fn bootstrap<T>(&self, target: T) -> Option<bt_dht_lookup::Lookup<T>>
    where
        T: Target,
    {
        let bootstrap = self.table.read().get_closest(target.to_id());
        if !bootstrap.is_empty() {
            return Some(bt_dht_lookup::Lookup::new(
                self.self_id.clone(),
                target,
                bootstrap,
            ));
        }

        let mut bootstrap_nodes = HashSet::new();
        for bootstrap in &*self.bootstrap {
            let endpoints = match net::lookup_host(bootstrap).await {
                Ok(endpoints) => endpoints,
                Err(error) => {
                    tracing::warn!(%bootstrap, %error);
                    continue;
                }
            };
            for endpoint in endpoints {
                // TODO: Support IPv6.
                if endpoint.is_ipv6() {
                    continue;
                }
                match self.reqrep.find_node_raw(endpoint, target.to_id()).await {
                    Ok(nodes) => bootstrap_nodes.extend(nodes.into_iter()),
                    Err(error) => tracing::warn!(%bootstrap, %endpoint, %error),
                }
            }
        }

        if bootstrap_nodes.is_empty() {
            tracing::warn!("bootstrap: no result");
            None
        } else {
            Some(bt_dht_lookup::Lookup::new(
                self.self_id.clone(),
                target,
                bootstrap_nodes,
            ))
        }
    }
}
