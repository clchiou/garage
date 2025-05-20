use std::collections::BTreeMap;

use serde_bytes::Bytes;

use bittorrent_bencode::{
    borrow,
    convert::{from_bytes, from_dict, to_bytes, to_dict, to_int},
    dict::{DictionaryInsert, DictionaryRemove},
    own,
};

use crate::message::{
    Error,
    query::{AnnouncePeer, FindNode, GetPeers, Ping, Query},
};

use super::{
    QUERY,
    convert::{to_id, to_info_hash},
};

const PING: &[u8] = b"ping";
const FIND_NODE: &[u8] = b"find_node";
const GET_PEERS: &[u8] = b"get_peers";
const ANNOUNCE_PEER: &[u8] = b"announce_peer";

const ARGUMENTS: &[u8] = b"a";

const ID: &[u8] = b"id";
const IMPLIED_PORT: &[u8] = b"implied_port";
const INFO_HASH: &[u8] = b"info_hash";
const PORT: &[u8] = b"port";
const TARGET: &[u8] = b"target";
const TOKEN: &[u8] = b"token";

impl<'a> TryFrom<&mut BTreeMap<&'a [u8], borrow::Value<'a>>> for Query<'a> {
    type Error = Error;

    fn try_from(dict: &mut BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        let method_name = dict.must_remove::<Error>(QUERY).and_then(to_bytes)?;
        let (arguments, _) = dict.must_remove::<Error>(ARGUMENTS).and_then(to_dict)?;
        match method_name {
            PING => Ok(Self::Ping(Ping::try_from(arguments)?)),
            FIND_NODE => Ok(Self::FindNode(FindNode::try_from(arguments)?)),
            GET_PEERS => Ok(Self::GetPeers(GetPeers::try_from(arguments)?)),
            ANNOUNCE_PEER => Ok(Self::AnnouncePeer(AnnouncePeer::try_from(arguments)?)),
            _ => Err(Error::UnknownMethodName {
                method_name: Vec::from(method_name),
            }),
        }
    }
}

impl<'a> From<Query<'a>> for BTreeMap<&'a Bytes, own::Value> {
    fn from(query: Query<'a>) -> Self {
        let (method_name, arguments): (_, BTreeMap<own::ByteString, own::Value>) = match query {
            Query::Ping(ping) => (PING, ping.into()),
            Query::FindNode(find_node) => (FIND_NODE, find_node.into()),
            Query::GetPeers(get_peers) => (GET_PEERS, get_peers.into()),
            Query::AnnouncePeer(announce_peer) => (ANNOUNCE_PEER, announce_peer.into()),
        };
        Self::from([
            (Bytes::new(QUERY), from_bytes(method_name)),
            (Bytes::new(ARGUMENTS), arguments.into()),
        ])
    }
}

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for Ping<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        Ok(Self {
            id: dict.must_remove(ID).and_then(to_id)?,
            extra: dict,
        })
    }
}

impl<'a> From<Ping<'a>> for BTreeMap<own::ByteString, own::Value> {
    fn from(ping: Ping<'a>) -> Self {
        let mut dict = Self::from([(own::ByteString::from(ID), from_bytes(ping.id))]);
        dict.append(&mut from_dict(ping.extra, own::ByteString::from));
        dict
    }
}

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for FindNode<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        Ok(Self {
            id: dict.must_remove(ID).and_then(to_id)?,
            target: dict.must_remove(TARGET).and_then(to_id)?,
            extra: dict,
        })
    }
}

impl<'a> From<FindNode<'a>> for BTreeMap<own::ByteString, own::Value> {
    fn from(find_node: FindNode<'a>) -> Self {
        let mut dict = Self::from([
            (own::ByteString::from(ID), from_bytes(find_node.id)),
            (own::ByteString::from(TARGET), from_bytes(find_node.target)),
        ]);
        dict.append(&mut from_dict(find_node.extra, own::ByteString::from));
        dict
    }
}

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for GetPeers<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        Ok(Self {
            id: dict.must_remove(ID).and_then(to_id)?,
            info_hash: dict.must_remove(INFO_HASH).and_then(to_info_hash)?,
            extra: dict,
        })
    }
}

impl<'a> From<GetPeers<'a>> for BTreeMap<own::ByteString, own::Value> {
    fn from(get_peers: GetPeers<'a>) -> Self {
        let mut dict = Self::from([
            (own::ByteString::from(ID), from_bytes(get_peers.id)),
            (
                own::ByteString::from(INFO_HASH),
                from_bytes(get_peers.info_hash),
            ),
        ]);
        dict.append(&mut from_dict(get_peers.extra, own::ByteString::from));
        dict
    }
}

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for AnnouncePeer<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        Ok(Self {
            id: dict.must_remove(ID).and_then(to_id)?,
            info_hash: dict.must_remove(INFO_HASH).and_then(to_info_hash)?,
            port: dict
                .must_remove(PORT)
                .and_then(to_int)
                .and_then(|port| port.try_into().map_err(|_| Error::InvalidNodePort { port }))?,
            implied_port: dict
                .remove(IMPLIED_PORT)
                .map(to_int::<Error>)
                .transpose()?
                .map(|implied_port| implied_port != 0),
            token: dict.must_remove::<Error>(TOKEN).and_then(to_bytes)?,
            extra: dict,
        })
    }
}

impl<'a> From<AnnouncePeer<'a>> for BTreeMap<own::ByteString, own::Value> {
    fn from(announce_peer: AnnouncePeer<'a>) -> Self {
        let mut dict = Self::from([
            (own::ByteString::from(ID), from_bytes(announce_peer.id)),
            (
                own::ByteString::from(INFO_HASH),
                from_bytes(announce_peer.info_hash),
            ),
            (
                own::ByteString::from(PORT),
                i64::from(announce_peer.port).into(),
            ),
            (
                own::ByteString::from(TOKEN),
                from_bytes(announce_peer.token),
            ),
        ]);
        dict.insert_from(IMPLIED_PORT, announce_peer.implied_port, |implied_port| {
            i64::from(implied_port).into()
        });
        dict.append(&mut from_dict(announce_peer.extra, own::ByteString::from));
        dict
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for Query<'a> {
        type Error = Error;

        fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Error> {
            Self::try_from(&mut dict)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{super::test_harness::*, *};

    #[test]
    fn query() {
        test_ok(
            [
                (b"q", new_bytes(b"find_node")),
                (
                    b"a",
                    new_btree_map([
                        (b"id", new_bytes(TEST_ID)),
                        (b"target", new_bytes(TEST_ID)),
                        (b"foo bar", 0.into()),
                    ])
                    .into(),
                ),
            ],
            Query::FindNode(FindNode {
                id: TEST_ID,
                target: TEST_ID,
                extra: new_btree_map([(b"foo bar", 0.into())]),
            }),
        );
        test_ok(
            [
                (b"q", new_bytes(b"get_peers")),
                (
                    b"a",
                    new_btree_map([
                        (b"id", new_bytes(TEST_ID)),
                        (b"info_hash", new_bytes(TEST_ID)),
                        (b"foo bar", 0.into()),
                    ])
                    .into(),
                ),
            ],
            Query::GetPeers(GetPeers {
                id: TEST_ID,
                info_hash: TEST_ID,
                extra: new_btree_map([(b"foo bar", 0.into())]),
            }),
        );
        test_ok(
            [
                (b"q", new_bytes(b"announce_peer")),
                (
                    b"a",
                    new_btree_map([
                        (b"id", new_bytes(TEST_ID)),
                        (b"info_hash", new_bytes(TEST_ID)),
                        (b"port", 8000.into()),
                        (b"implied_port", 1.into()),
                        (b"token", new_bytes(b"some token")),
                        (b"foo bar", 0.into()),
                    ])
                    .into(),
                ),
            ],
            Query::AnnouncePeer(AnnouncePeer {
                id: TEST_ID,
                info_hash: TEST_ID,
                port: 8000,
                implied_port: Some(true),
                token: b"some token",
                extra: new_btree_map([(b"foo bar", 0.into())]),
            }),
        );
        test_err::<Query, _>(
            [
                (b"q", new_bytes(b"no-such-method")),
                (b"a", BTreeMap::new().into()),
            ],
            Error::UnknownMethodName {
                method_name: b"no-such-method".to_vec(),
            },
        );
        test_err::<Query, _>(
            [
                (b"q", new_bytes(b"announce_peer")),
                (
                    b"a",
                    new_btree_map([
                        (b"id", new_bytes(TEST_ID)),
                        (b"info_hash", new_bytes(TEST_ID)),
                        (b"port", 65536.into()),
                        (b"implied_port", 1.into()),
                        (b"token", new_bytes(b"some token")),
                        (b"foo bar", 0.into()),
                    ])
                    .into(),
                ),
            ],
            Error::InvalidNodePort { port: 65536 },
        );
    }
}
