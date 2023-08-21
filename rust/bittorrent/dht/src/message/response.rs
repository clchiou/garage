use std::collections::BTreeMap;
use std::net::{SocketAddr, SocketAddrV4};

use bytes::{Bytes, BytesMut};

use g1_base::fmt::{DebugExt, Hex};

use bittorrent_base::{
    compact::{self, Compact},
    NODE_ID_SIZE,
};
use bittorrent_bencode::{borrow, FormatDictionary};

use crate::{message, NodeContactInfo, NodeId};

g1_base::define_owner!(#[derive(Debug)] pub(crate) PingOwner for Ping);
g1_base::impl_owner_try_from!(message::MessageOwner for PingOwner);

g1_base::define_owner!(#[derive(Debug)] pub(crate) FindNodeOwner for FindNode);
g1_base::impl_owner_try_from!(message::MessageOwner for FindNodeOwner);

g1_base::define_owner!(#[derive(Debug)] pub(crate) GetPeersOwner for GetPeers);
g1_base::impl_owner_try_from!(message::MessageOwner for GetPeersOwner);

g1_base::define_owner!(#[derive(Debug)] pub(crate) AnnouncePeerOwner for AnnouncePeer);
g1_base::impl_owner_try_from!(message::MessageOwner for AnnouncePeerOwner);

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub(crate) struct Response<'a> {
    #[debug(with = FormatDictionary)]
    pub(super) response: BTreeMap<&'a [u8], borrow::Value<'a>>,
    #[debug(with = Hex)]
    pub(crate) requester: Option<&'a [u8]>,
}

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub(crate) struct Ping<'a> {
    #[debug(with = Hex)]
    pub(crate) id: &'a [u8],

    #[debug(with = FormatDictionary)]
    pub(crate) extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub(crate) struct FindNode<'a> {
    #[debug(with = Hex)]
    pub(crate) id: &'a [u8],
    #[debug(with = Hex)]
    pub(super) nodes: &'a [u8],

    #[debug(with = FormatDictionary)]
    pub(crate) extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub(crate) struct GetPeers<'a> {
    #[debug(with = Hex)]
    pub(crate) id: &'a [u8],
    // While BEP 5 appears to specify that `token` must be present, some implementations do not
    // adhere to this aspect of BEP 5.
    #[debug(with = Hex)]
    pub(crate) token: Option<&'a [u8]>,
    // While BEP 5 appears to specify that `values` and `nodes` should be "either or", some
    // implementations still return both.
    #[debug(with = Hex)]
    pub(super) values: Option<Vec<&'a [u8]>>,
    #[debug(with = Hex)]
    pub(super) nodes: Option<&'a [u8]>,

    #[debug(with = FormatDictionary)]
    pub(crate) extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub(crate) struct AnnouncePeer<'a> {
    #[debug(with = Hex)]
    pub(crate) id: &'a [u8],

    #[debug(with = FormatDictionary)]
    pub(crate) extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

// Do NOT `derive(Snafu)` since this is not a typical error type.
#[derive(Clone, Debug, Eq, PartialEq)]
// Keep the "Error" suffix to be consistent with BEP 5.
#[allow(clippy::enum_variant_names)]
pub(crate) enum Error<'a> {
    GenericError { message: &'a str },
    ServerError { message: &'a str },
    ProtocolError { message: &'a str },
    MethodUnknown { message: &'a str },
}

impl<'a> Response<'a> {
    pub(crate) fn new(response: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Self {
        Self {
            response,
            requester: None, // TODO: Supply self endpoint, as specified in BEP 42.
        }
    }
}

impl<'a> Ping<'a> {
    pub(crate) fn new(id: &'a [u8]) -> Self {
        Self {
            id,
            extra: BTreeMap::new(),
        }
    }
}

impl<'a> FindNode<'a> {
    pub(crate) fn new(id: &'a [u8], nodes: &'a [u8]) -> Self {
        Self {
            id,
            nodes,
            extra: BTreeMap::new(),
        }
    }

    // TODO: Add `decode_nodes_v6`.
    pub(crate) fn decode_nodes_v4(&self) -> Result<Vec<NodeContactInfo>, message::Error> {
        decode_nodes::<SocketAddrV4>(self.nodes)
    }

    // TODO: Add `encode_nodes_v6`.
    pub(crate) fn encode_nodes_v4<'b>(
        nodes: impl Iterator<Item = &'b NodeContactInfo>,
    ) -> BytesMut {
        encode_nodes(nodes, to_v4)
    }
}

impl<'a> GetPeers<'a> {
    pub(crate) fn new(
        id: &'a [u8],
        token: Option<&'a [u8]>,
        values: Option<Vec<&'a [u8]>>,
        nodes: Option<&'a [u8]>,
    ) -> Self {
        Self {
            id,
            token,
            values,
            nodes,
            extra: BTreeMap::new(),
        }
    }

    // TODO: Add `decode_peers_v6`.
    pub(crate) fn decode_peers_v4(&self) -> Option<Result<Vec<SocketAddr>, message::Error>> {
        Some(decode_peers::<SocketAddrV4>(self.values.as_ref()?))
    }

    // TODO: Add `encode_peers_v6`.
    pub(crate) fn encode_peers_v4(peers: impl Iterator<Item = SocketAddr>) -> Vec<Bytes> {
        encode_peers(peers, to_v4)
    }

    // TODO: Add `decode_nodes_v6`.
    pub(crate) fn decode_nodes_v4(&self) -> Option<Result<Vec<NodeContactInfo>, message::Error>> {
        Some(decode_nodes::<SocketAddrV4>(self.nodes?))
    }

    // TODO: Add `encode_nodes_v6`.
    pub(crate) fn encode_nodes_v4<'b>(
        nodes: impl Iterator<Item = &'b NodeContactInfo>,
    ) -> BytesMut {
        encode_nodes(nodes, to_v4)
    }
}

impl<'a> AnnouncePeer<'a> {
    pub(crate) fn new(id: &'a [u8]) -> Self {
        Self {
            id,
            extra: BTreeMap::new(),
        }
    }
}

impl From<compact::Error> for message::Error {
    fn from(error: compact::Error) -> Self {
        match error {
            compact::Error::ExpectSize { size, expect } => {
                message::Error::ExpectCompactSize { size, expect }
            }
            compact::Error::ExpectArraySize { size, unit_size } => {
                message::Error::ExpectCompactArraySize { size, unit_size }
            }
        }
    }
}

fn decode_peers<T>(peers: &[&[u8]]) -> Result<Vec<SocketAddr>, message::Error>
where
    T: Compact,
    SocketAddr: From<T>,
{
    peers
        .iter()
        .copied()
        .map(T::decode)
        .map(|result| result.map(SocketAddr::from))
        .try_collect()
        .map_err(message::Error::from)
}

fn encode_peers<T, F>(peers: impl Iterator<Item = SocketAddr>, to_endpoint: F) -> Vec<Bytes>
where
    T: Compact,
    F: Fn(SocketAddr) -> T,
{
    let mut buffer = BytesMut::new();
    T::encode_many(peers.map(to_endpoint), &mut buffer);
    T::split_buffer(buffer.freeze()).unwrap().collect()
}

fn decode_nodes<T>(nodes: &[u8]) -> Result<Vec<NodeContactInfo>, message::Error>
where
    T: Compact,
    SocketAddr: From<T>,
{
    <([u8; NODE_ID_SIZE], T)>::decode_many(nodes)
        .map_err(message::Error::from)?
        .map(|result| {
            result.map(|(node_id, endpoint)| (NodeId::new(node_id), endpoint.into()).into())
        })
        .try_collect()
        .map_err(message::Error::from)
}

fn encode_nodes<'a, T, F>(
    nodes: impl Iterator<Item = &'a NodeContactInfo>,
    to_endpoint: F,
) -> BytesMut
where
    T: Compact,
    F: Fn(SocketAddr) -> T,
{
    let mut buffer = BytesMut::new();
    <(&[u8; NODE_ID_SIZE], T)>::encode_many(
        nodes.map(|node| (node.id.as_array(), to_endpoint(node.endpoint))),
        &mut buffer,
    );
    buffer
}

fn to_v4(endpoint: SocketAddr) -> SocketAddrV4 {
    match endpoint {
        SocketAddr::V4(endpoint) => endpoint,
        SocketAddr::V6(_) => std::unreachable!(),
    }
}

#[cfg(test)]
mod tests {
    use hex_literal::hex;

    use super::*;

    #[test]
    fn compact() {
        let node_id = NodeId::new(hex!("0123456789abcdef 0123456789abcdef 01234567"));
        let endpoint = "127.0.0.1:8000".parse().unwrap();
        let nodes = vec![(node_id, endpoint).into()];
        let compact_endpoint = hex!("7f000001 1f40").as_slice();
        let compact_nodes =
            hex!("0123456789abcdef 0123456789abcdef 01234567 7f000001 1f40").as_slice();

        let find_node = FindNode::new(&[], &[]);
        assert_eq!(find_node.decode_nodes_v4(), Ok(Vec::new()));
        assert_eq!(FindNode::encode_nodes_v4([].iter()), b"".as_slice());

        let find_node = FindNode::new(&[], compact_nodes);
        assert_eq!(find_node.decode_nodes_v4(), Ok(nodes.clone()));
        assert_eq!(FindNode::encode_nodes_v4(nodes.iter()), compact_nodes);

        let get_peers = GetPeers::new(&[], None, None, None);
        assert_eq!(get_peers.decode_peers_v4(), None);
        assert_eq!(get_peers.decode_nodes_v4(), None);

        let get_peers = GetPeers::new(&[], None, Some(Vec::new()), Some(&[]));
        assert_eq!(get_peers.decode_peers_v4(), Some(Ok(Vec::new())));
        assert_eq!(get_peers.decode_nodes_v4(), Some(Ok(Vec::new())));
        assert_eq!(
            GetPeers::encode_peers_v4([].into_iter()),
            Vec::<Bytes>::new(),
        );
        assert_eq!(GetPeers::encode_nodes_v4([].into_iter()), b"".as_slice());

        let get_peers = GetPeers::new(&[], None, Some(vec![compact_endpoint]), Some(compact_nodes));
        assert_eq!(get_peers.decode_peers_v4(), Some(Ok(vec![endpoint])));
        assert_eq!(get_peers.decode_nodes_v4(), Some(Ok(nodes.clone())));
        assert_eq!(
            GetPeers::encode_peers_v4([endpoint].into_iter()),
            vec![Bytes::from_static(compact_endpoint)],
        );
        assert_eq!(GetPeers::encode_nodes_v4(nodes.iter()), compact_nodes);
    }
}
