use std::collections::{BTreeMap, BTreeSet};
use std::io::Error;
use std::sync::Arc;

use bytes::Bytes;
use tokio::sync::mpsc;

use g1_base::{fmt::Hex, sync::MutexExt};
use g1_tokio::task::Cancel;

use bittorrent_bencode::{borrow, serde as serde_bencode, FormatDictionary};

use crate::{
    kbucket::KBucketItem,
    message::{query, response, Message, MessageOwner, Payload},
    reqrep::{Endpoint, Sender},
    routing::KBucketFull,
    token::{Token, TokenSource},
};

use super::NodeState;

#[derive(Debug)]
pub(super) struct Handler {
    cancel: Cancel,
    state: NodeState,
    token_src: Arc<TokenSource>,
    kbucket_full_send: mpsc::Sender<KBucketFull>,
    endpoint: Endpoint,
    request: MessageOwner<Bytes>,
    response_send: Sender,
}

impl Handler {
    pub(super) fn new(
        cancel: Cancel,
        state: NodeState,
        token_src: Arc<TokenSource>,
        kbucket_full_send: mpsc::Sender<KBucketFull>,
        endpoint: Endpoint,
        request: MessageOwner<Bytes>,
        response_send: Sender,
    ) -> Self {
        Self {
            cancel,
            state,
            token_src,
            kbucket_full_send,
            endpoint,
            request,
            response_send,
        }
    }

    #[tracing::instrument(name = "dht", fields(peer_endpoint = ?self.endpoint.0), skip_all)]
    pub(super) async fn run(self) -> Result<(), Error> {
        let request = self.request.deref();
        if !request.extra.is_empty() {
            tracing::trace!(request.extra = ?FormatDictionary(&request.extra));
        }

        let response = match &request.payload {
            Payload::Query(query) => self.handle_query(query)?,
            Payload::Response(response) => {
                tracing::warn!(?response, "expect query");
                self.to_bytes(Payload::Error(new_expect_query_error()))?
            }
            Payload::Error(error) => {
                tracing::warn!(?error, "expect query");
                self.to_bytes(Payload::Error(new_expect_query_error()))?
            }
        };

        tokio::select! {
            () = self.cancel.wait() => {
                tracing::debug!("dht handler is cancelled");
                Ok(())
            }
            result = self.response_send.send((self.endpoint.clone(), response)) => result,
        }
    }

    fn handle_query(&self, query: &query::Query) -> Result<Bytes, Error> {
        tracing::trace!(?query);
        let extra = query.extra();
        if !extra.is_empty() {
            tracing::trace!(query.extra = ?FormatDictionary(extra));
        }

        {
            let mut routing = self.state.routing.must_lock();
            let item = KBucketItem::new((query.id().try_into().unwrap(), self.endpoint.0).into());
            if let Err(full) = routing.insert(item) {
                tracing::info!("kbucket full");
                // We make our best effort to notify the server that a `KBucket` is full.
                let _ = self.kbucket_full_send.try_send(full);
            }
        }

        match query {
            query::Query::Ping(ping) => self.handle_ping(ping),
            query::Query::FindNode(find_node) => self.handle_find_node(find_node),
            query::Query::GetPeers(get_peers) => self.handle_get_peers(get_peers),
            query::Query::AnnouncePeer(announce_peer) => self.handle_announce_peer(announce_peer),
        }
    }

    fn handle_ping(&self, _: &query::Ping) -> Result<Bytes, Error> {
        self.encode_response(response::Ping::new(self.id()))
    }

    fn handle_find_node(&self, find_node: &query::FindNode) -> Result<Bytes, Error> {
        let nodes = self
            .state
            .routing
            .must_lock()
            .get_closest(find_node.target_bits());
        let nodes = response::FindNode::encode_nodes_v4(nodes.iter()).freeze();
        self.encode_response(response::FindNode::new(self.id(), &nodes))
    }

    fn handle_get_peers(&self, get_peers: &query::GetPeers) -> Result<Bytes, Error> {
        let token = self.generate_token();
        let (values, nodes) = {
            // You must maintain the locking order.
            let routing = self.state.routing.must_lock();
            let peers = self.state.peers.must_lock();
            match peers.get(get_peers.info_hash) {
                Some(peers) => (
                    Some(response::GetPeers::encode_peers_v4(peers.iter().copied())),
                    None,
                ),
                None => {
                    let nodes = routing.get_closest(get_peers.info_hash_bits());
                    let nodes = response::GetPeers::encode_nodes_v4(nodes.iter()).freeze();
                    (None, Some(nodes))
                }
            }
        };
        self.encode_response(response::GetPeers::new(
            self.id(),
            Some(&token),
            values
                .as_ref()
                .map(|values| values.iter().map(Bytes::as_ref).collect()),
            nodes.as_deref(),
        ))
    }

    fn handle_announce_peer(&self, announce_peer: &query::AnnouncePeer) -> Result<Bytes, Error> {
        if !self.validate_token(announce_peer.token) {
            tracing::warn!(announce_peer.token = ?Hex(announce_peer.token), "invalid token");
            return self.to_bytes(Payload::Error(response::Error::ProtocolError {
                message: "invalid token",
            }));
        }

        let info_hash = announce_peer.info_hash.try_into().unwrap();
        let mut peer = self.endpoint.0;
        if !announce_peer.implied_port.unwrap_or(false) {
            peer.set_port(announce_peer.port);
        }
        tracing::info!(?info_hash, ?peer, "accept announce_peer");
        self.state
            .peers
            .must_lock()
            .entry(info_hash)
            .or_insert_with(BTreeSet::new)
            .insert(peer);
        self.encode_response(response::AnnouncePeer::new(self.id()))
    }

    fn id(&self) -> &[u8] {
        self.state.self_id.as_ref()
    }

    fn generate_token(&self) -> Token {
        self.token_src.generate(self.endpoint.0)
    }

    fn validate_token(&self, token: &[u8]) -> bool {
        self.token_src.validate(self.endpoint.0, token)
    }

    fn encode_response<'a, T>(&self, response: T) -> Result<Bytes, Error>
    where
        T: Into<BTreeMap<&'a [u8], borrow::Value<'a>>>,
        T: 'a,
    {
        self.to_bytes(Payload::Response(response::Response::new(response.into())))
    }

    fn to_bytes(&self, payload: Payload) -> Result<Bytes, Error> {
        match serde_bencode::to_bytes(&Message::new(&self.endpoint.1, payload)) {
            Ok(bytes) => Ok(bytes.freeze()),
            Err(error) => Err(Error::other(error)),
        }
    }
}

fn new_expect_query_error() -> response::Error<'static> {
    response::Error::ProtocolError {
        message: "expect query",
    }
}
