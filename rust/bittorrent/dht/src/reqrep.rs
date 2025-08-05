use std::collections::BTreeMap;
use std::io::Error;
use std::net::SocketAddr;
use std::sync::Arc;

use bytes::Bytes;
use futures::{
    future,
    sink::{Sink, SinkExt},
    stream::{Stream, StreamExt},
};

use g1_base::fmt::{DebugExt, Hex};
use g1_msg::reqrep;

use bittorrent_bencode::{FormatDictionary, borrow, serde as serde_bencode};

use crate::{
    NodeContactInfo, NodeId,
    message::{self, Message, MessageOwner, Payload, query, response},
};

pub(crate) struct DhtProtocol;

impl reqrep::Protocol for DhtProtocol {
    type Id = Endpoint;
    type Incoming = Incoming;
    type Outgoing = Outgoing;

    type Error = Error;

    fn incoming_id((endpoint, _): &Self::Incoming) -> Self::Id {
        endpoint.clone()
    }

    fn outgoing_id((endpoint, _): &Self::Outgoing) -> Self::Id {
        endpoint.clone()
    }
}

pub(crate) type ReqRepGuard = reqrep::Guard<DhtProtocol>;

pub(crate) type ReqRep = reqrep::ReqRep<DhtProtocol>;
pub(crate) type Sender = reqrep::ResponseSend<DhtProtocol>;
pub(crate) type Incoming = (Endpoint, MessageOwner<Bytes>);
pub(crate) type Outgoing = (Endpoint, Bytes);

#[derive(Clone, DebugExt, Eq, Hash, PartialEq)]
pub(crate) struct Endpoint(
    pub(crate) SocketAddr,
    #[debug(with = Hex)] pub(crate) Arc<[u8]>,
);

pub(crate) fn spawn<I, O>(incoming: I, outgoing: O) -> (ReqRep, ReqRepGuard)
where
    I: Stream<Item = Result<(SocketAddr, Bytes), Error>> + Send + Unpin + 'static,
    O: Sink<(SocketAddr, Bytes), Error = Error> + Send + Unpin + 'static,
{
    ReqRep::spawn(
        incoming.map(|raw_message| {
            raw_message.and_then(|(raw_endpoint, raw_payload)| {
                let payload = MessageOwner::try_from(raw_payload).map_err(Error::other)?;
                Ok((Endpoint(raw_endpoint, payload.deref().txid.into()), payload))
            })
        }),
        outgoing.with(|(Endpoint(raw_endpoint, _), raw_payload)| {
            future::ok((raw_endpoint, raw_payload))
        }),
    )
}

#[derive(Debug)]
pub(crate) struct Client {
    reqrep: ReqRep,
    self_id: NodeId,
    peer_endpoint: SocketAddr,
}

pub(crate) type Nodes = Vec<NodeContactInfo>;

pub(crate) type GetPeers = (Option<Token>, Option<Peers>, Option<Nodes>);
pub(crate) type Token = Bytes;
pub(crate) type Peers = Vec<SocketAddr>;

impl Client {
    pub(crate) fn new(reqrep: ReqRep, self_id: NodeId, peer_endpoint: SocketAddr) -> Self {
        Self {
            reqrep,
            self_id,
            peer_endpoint,
        }
    }

    async fn transact<T>(&self, query: query::Query<'_>) -> Result<T, Error>
    where
        T: TryFrom<MessageOwner<Bytes>, Error = message::Error>,
    {
        let peer_endpoint = Endpoint(self.peer_endpoint, Arc::from(Message::new_txid()));
        let request = Message::new(&peer_endpoint.1, Payload::Query(query));
        tracing::trace!(?request, "->peer");

        let request = serde_bencode::to_bytes(&request)
            .map_err(Error::other)?
            .freeze();
        let (_, response_owner) = self
            .reqrep
            .request((peer_endpoint, request))
            .await
            .ok_or_else(|| Error::other("dht reqrep exit"))?
            .await
            .map_err(Error::other)?;

        let response = response_owner.deref();
        tracing::trace!(?response, "peer->");
        if !response.extra.is_empty() {
            tracing::trace!(response.extra = ?FormatDictionary(&response.extra));
        }
        if let Payload::Error(error) = &response.payload {
            return Err(Error::other(format!("peer returns error: {error:?}")));
        }

        response_owner.try_into().map_err(Error::other)
    }

    pub(crate) async fn ping(&self) -> Result<(), Error> {
        let response_owner: response::PingOwner<Bytes> = self
            .transact(query::Query::Ping(query::Ping::new(self.self_id.as_ref())))
            .await?;
        let response = response_owner.deref();
        log_body_extra(&response.extra);
        Ok(())
    }

    pub(crate) async fn find_node(&self, target: &[u8]) -> Result<Nodes, Error> {
        let response_owner: response::FindNodeOwner<Bytes> = self
            .transact(query::Query::FindNode(query::FindNode::new(
                self.self_id.as_ref(),
                target,
            )))
            .await?;
        let response = response_owner.deref();
        log_body_extra(&response.extra);
        response.decode_nodes_v4().map_err(Error::other)
    }

    pub(crate) async fn get_peers(&self, info_hash: &[u8]) -> Result<GetPeers, Error> {
        let response_owner: response::GetPeersOwner<Bytes> = self
            .transact(query::Query::GetPeers(query::GetPeers::new(
                self.self_id.as_ref(),
                info_hash,
            )))
            .await?;
        let response = response_owner.deref();
        log_body_extra(&response.extra);
        Ok((
            response.token.map(Token::copy_from_slice),
            response
                .decode_peers_v4()
                .transpose()
                .map_err(Error::other)?,
            response
                .decode_nodes_v4()
                .transpose()
                .map_err(Error::other)?,
        ))
    }

    pub(crate) async fn announce_peer(
        &self,
        info_hash: &[u8],
        port: u16,
        implied_port: Option<bool>,
        token: &[u8],
    ) -> Result<(), Error> {
        let response_owner: response::AnnouncePeerOwner<Bytes> = self
            .transact(query::Query::AnnouncePeer(query::AnnouncePeer::new(
                self.self_id.as_ref(),
                info_hash,
                port,
                implied_port,
                token,
            )))
            .await?;
        let response = response_owner.deref();
        log_body_extra(&response.extra);
        Ok(())
    }
}

fn log_body_extra(extra: &BTreeMap<&[u8], borrow::Value<'_>>) {
    if !extra.is_empty() {
        tracing::trace!(response_body.extra = ?FormatDictionary(extra));
    }
}
