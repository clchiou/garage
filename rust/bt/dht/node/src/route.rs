use std::sync::{Arc, Mutex};

use g1_base::sync::MutexExt;
use g1_tokio::task::JoinGuard;

use bt_base::NodeId;
use bt_dht_proto::{AnnouncePeer, Error, GetPeers, NodeInfo, Query, Response};
use bt_dht_reqrep::{ReqRep, ResponseSend};
use bt_model::{Model, TorrentRemoved};

use crate::table::Table;
use crate::token::Issuer;

struct Router {
    table: Arc<Table>,
    reqrep: ReqRep,
    model: Arc<Mutex<Model>>,
    issuer: Issuer,
}

pub(crate) type RouterGuard = JoinGuard<()>;

pub(crate) fn spawn(
    table: Arc<Table>,
    reqrep: ReqRep,
    model: Arc<Mutex<Model>>,
    issuer: Issuer,
) -> RouterGuard {
    RouterGuard::spawn(move |cancel| {
        let mut router = RouterLoop::new(
            cancel,
            Router {
                table,
                reqrep,
                model,
                issuer,
            },
        );
        async move { router.run().await }
    })
}

#[g1_actor::actor]
impl Router {
    #[actor::loop_(react = {
        let incoming = self.reqrep.accept();
        match incoming {
            Some((query, response_send)) => self.accept(query, response_send).await,
            None => break,
        }
    })]
    async fn accept(&self, query: Query, response_send: ResponseSend) {
        //
        // BEP 5 specifies that a routing table should only contain good nodes (i.e., nodes that
        // respond to our queries).  Therefore, we only update the routing table, rather than
        // inserting the querying node, because a node may be able to send queries but not receive
        // them.
        //

        let node = NodeInfo {
            id: query.id(),
            endpoint: response_send.node_endpoint(),
        };
        match query {
            Query::Ping(_) => {
                response_send.send(Response::ping).await;

                self.table.write().update_ok(node);
            }

            Query::FindNode(find_node) => {
                let nodes = self.table.read().get_closest(find_node.target).into();

                response_send
                    .send(|txid, self_id| Response::find_node(txid, self_id, nodes))
                    .await;

                self.table.write().update_ok(node);
            }

            Query::GetPeers(get_peers) => {
                let GetPeers { info_hash, .. } = get_peers;

                let token = self.issuer.issue(response_send.node_endpoint());

                let peers = match self.model.must_lock().peers().peers(info_hash.clone()) {
                    Ok(peers) => {
                        let peers = peers
                            .map(|(_, peer_endpoint)| peer_endpoint)
                            .collect::<Vec<_>>();
                        (!peers.is_empty()).then_some(peers)
                    }
                    Err(error @ TorrentRemoved) => {
                        let peer_endpoint = response_send.node_endpoint();
                        tracing::info!(?node, %info_hash, %peer_endpoint, %error, "get_peers");
                        None
                    }
                };

                let nodes = self.table.read().get_closest(NodeId::pretend(info_hash));
                let nodes = (!nodes.is_empty()).then(|| nodes.into());

                response_send
                    .send(move |txid, self_id| {
                        Response::get_peers(txid, self_id, token, peers, nodes)
                    })
                    .await;

                self.table.write().update_ok(node);
            }

            Query::AnnouncePeer(announce_peer) => {
                let AnnouncePeer {
                    implied_port,
                    info_hash,
                    port,
                    token,
                    ..
                } = announce_peer;

                if self.issuer.verify(node.endpoint, token) {
                    let mut peer_endpoint = response_send.node_endpoint();
                    if !implied_port.unwrap_or(false) {
                        peer_endpoint.set_port(port);
                    }
                    match self
                        .model
                        .must_lock()
                        .peers_mut()
                        .insert(info_hash.clone(), peer_endpoint)
                    {
                        Ok(_) => {
                            tracing::info!(?node, %info_hash, %peer_endpoint, "announce_peer");
                        }
                        Err(error @ TorrentRemoved) => {
                            tracing::info!(
                                ?node, %info_hash, %peer_endpoint, %error, "announce_peer",
                            );
                        }
                    }

                    response_send.send(Response::announce_peer).await;

                    self.table.write().update_ok(node);
                } else {
                    tracing::warn!(?node, %info_hash, "announce_peer: bad token");

                    response_send.send(|txid, _| Error::protocol(txid)).await;

                    self.table.write().update_err(node.id);
                }
            }
        }
    }
}
