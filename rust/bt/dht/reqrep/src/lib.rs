#![feature(type_alias_impl_trait)]

mod proto;

use std::net::SocketAddr;

use snafu::prelude::*;

use bt_base::node_id::NODE_ID_SIZE;
use bt_base::{InfoHash, NodeId, PeerEndpoint};
use bt_dht_proto::{
    Error as ProtocolError, FindNodeResponse, GetPeersResponse, Message, NodeInfo, Payload, Query,
    Response, Token, Txid,
};
use bt_udp::{Sink, Stream};

use crate::proto::ReqRepInner;

#[derive(Clone, Debug)]
pub struct ReqRep {
    self_id: NodeId,
    reqrep: ReqRepInner,
    // Placeholder id for error values.
    placeholder_id: NodeId,
}

pub use crate::proto::ReqRepGuard;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct GetPeers {
    pub peers: Option<Vec<PeerEndpoint>>,
    pub nodes: Option<Vec<NodeInfo>>,
    pub token: Option<Token>,
}

#[derive(Clone, Debug)]
pub struct ResponseSend {
    self_id: NodeId,
    node_endpoint: SocketAddr,
    txid: Txid,
    response_send: proto::ResponseSend,
}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("{detail} {node:?}"))]
pub struct Error {
    #[snafu(source)]
    detail: ErrorDetail,
    node: NodeInfo,
}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
enum ErrorDetail {
    #[snafu(display("no response"))]
    NoResponse,

    #[snafu(display("incorrect protocol sequence"))]
    IncorrectProtocol,
    #[snafu(display("protocol error: {error:?}"))]
    Protocol { error: ProtocolError },

    #[snafu(display("unexpected node id: {id}"))]
    UnexpectedNodeId { id: NodeId },

    #[snafu(display("invalid find_node response: {response:?}"))]
    InvalidFindNodeResponse { response: Response },
}

impl ReqRep {
    // TODO: Expose `g1_msg::reqrep::ReqRep::spawner` configuration.
    pub fn spawn<I, O>(self_id: NodeId, stream: I, sink: O) -> (Self, ReqRepGuard)
    where
        I: Stream,
        O: Sink,
    {
        let (reqrep, guard) = ReqRepInner::spawn(proto::decode(stream), proto::encode(sink));
        (
            Self {
                self_id,
                reqrep,
                placeholder_id: NodeId::from([0; NODE_ID_SIZE]),
            },
            guard,
        )
    }

    // We only allow querying a node without knowing its id in a few special cases, and in those
    // cases, a placeholder error context is used.
    fn placeholder(&self, node_endpoint: SocketAddr) -> Snafu<NodeInfo> {
        Snafu {
            node: NodeInfo {
                id: self.placeholder_id.clone(),
                endpoint: node_endpoint,
            },
        }
    }

    pub async fn accept(&self) -> Option<(Query, ResponseSend)> {
        loop {
            let ((node_endpoint, request), response_send) = self.reqrep.accept().await?;
            tracing::debug!(%node_endpoint, ?request, "accept");
            let (txid, query) = match request.payload {
                Payload::Query(query) => (request.txid, query),
                Payload::Response(_) | Payload::Error(_) => {
                    tracing::warn!(%node_endpoint, ?request, "accept: incorrect protocol sequence");
                    continue;
                }
            };
            return Some((
                query,
                ResponseSend::new(self.self_id.clone(), node_endpoint, txid, response_send),
            ));
        }
    }

    pub async fn ping(&self, node: NodeInfo) -> Result<(), Error> {
        self.request(node, Query::ping(self.self_id.clone()))
            .await
            .map(|Response { .. }| ())
    }

    // A peer may send us its DHT port, after which we ping it to obtain its id.
    pub async fn ping_raw(&self, node_endpoint: SocketAddr) -> Result<NodeId, Error> {
        self.request_raw(node_endpoint, Query::ping(self.self_id.clone()))
            .await
            .map(|Response { id, .. }| id)
    }

    pub async fn find_node(&self, node: NodeInfo, target: NodeId) -> Result<Vec<NodeInfo>, Error> {
        self.request(node.clone(), Query::find_node(self.self_id.clone(), target))
            .await
            .and_then(|response| Self::to_nodes(response).context(Snafu { node }))
    }

    // When bootstrapping, we query nodes without knowing their ids.
    pub async fn find_node_raw(
        &self,
        node_endpoint: SocketAddr,
        target: NodeId,
    ) -> Result<Vec<NodeInfo>, Error> {
        self.request_raw(
            node_endpoint,
            Query::find_node(self.self_id.clone(), target),
        )
        .await
        .and_then(|response| Self::to_nodes(response).context(self.placeholder(node_endpoint)))
    }

    #[allow(clippy::result_large_err)]
    fn to_nodes(response: Response) -> Result<Vec<NodeInfo>, ErrorDetail> {
        match FindNodeResponse::try_from(response) {
            Ok(response) => Ok(response.nodes),
            Err(response) => Err(ErrorDetail::InvalidFindNodeResponse { response }),
        }
    }

    pub async fn get_peers(&self, node: NodeInfo, info_hash: InfoHash) -> Result<GetPeers, Error> {
        self.request(node, Query::get_peers(self.self_id.clone(), info_hash))
            .await
            .map(|response| {
                let GetPeersResponse {
                    values: peers,
                    nodes,
                    token,
                    ..
                } = GetPeersResponse::from(response);
                GetPeers {
                    peers,
                    nodes,
                    token,
                }
            })
    }

    pub async fn announce_peer(
        &self,
        node: NodeInfo,
        implied_port: Option<bool>,
        info_hash: InfoHash,
        port: u16,
        token: Token,
    ) -> Result<(), Error> {
        self.request(
            node,
            Query::announce_peer(self.self_id.clone(), implied_port, info_hash, port, token),
        )
        .await
        .map(|Response { .. }| ())
    }

    pub async fn request(&self, node: NodeInfo, query: Message) -> Result<Response, Error> {
        self.request_impl(node.endpoint, query)
            .await
            .and_then(|response| {
                // Detect whether a node has changed its id or if our routing table is out of date.
                ensure!(
                    response.id == node.id,
                    UnexpectedNodeIdSnafu { id: response.id },
                );
                Ok(response)
            })
            .context(Snafu { node })
    }

    async fn request_raw(
        &self,
        node_endpoint: SocketAddr,
        query: Message,
    ) -> Result<Response, Error> {
        self.request_impl(node_endpoint, query)
            .await
            .context(self.placeholder(node_endpoint))
    }

    async fn request_impl(
        &self,
        node_endpoint: SocketAddr,
        query: Message,
    ) -> Result<Response, ErrorDetail> {
        tracing::debug!(%node_endpoint, ?query, "request");
        let (recv_endpoint, response) = self
            .reqrep
            .request((node_endpoint, query))
            .await
            .ok_or(ErrorDetail::NoResponse)?
            .await
            .map_err(|_| ErrorDetail::NoResponse)?;
        assert_eq!(recv_endpoint, node_endpoint);

        tracing::debug!(%node_endpoint, ?response, "request");
        match response.payload {
            Payload::Response(response) => Ok(response),
            Payload::Query(_) => Err(ErrorDetail::IncorrectProtocol),
            Payload::Error(error) => Err(ErrorDetail::Protocol { error }),
        }
    }
}

impl ResponseSend {
    fn new(
        self_id: NodeId,
        node_endpoint: SocketAddr,
        txid: Txid,
        response_send: proto::ResponseSend,
    ) -> Self {
        Self {
            self_id,
            node_endpoint,
            txid,
            response_send,
        }
    }

    pub fn node_endpoint(&self) -> SocketAddr {
        self.node_endpoint
    }

    pub async fn send<F>(self, f: F)
    where
        F: FnOnce(Txid, NodeId) -> Message,
    {
        self.response_send
            .send((self.node_endpoint, f(self.txid, self.self_id)))
            .await
    }
}
