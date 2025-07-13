mod flat;
mod info_hash;
mod node_id;
mod node_info;
mod peer_info;
mod reinsert;
mod requestor;

use bytes::Bytes;
use serde::{Deserialize, Serialize};

use bt_base::{InfoHash, NodeId};
use bt_bencode::Value;
use bt_serde::SerdeWith;

use crate::flat::FlatMessage;
use crate::node_id::NodeIdSerdeWith;
use crate::node_info::CompactNodeInfoListSerdeWithV4;
use crate::peer_info::CompactPeerInfoListSerdeWithV4;
use crate::reinsert::reinsert;

//
// Implementer's Notes: Based on our current use cases, making all fields `pub` seems to be the
// right decision.
//

pub use crate::node_info::NodeInfo;
pub use crate::peer_info::PeerInfo;
pub use crate::requestor::Requestor;

pub type Txid = Bytes;
pub type Token = Bytes;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(try_from = "FlatMessage", into = "FlatMessage")]
pub struct Message {
    pub txid: Txid,
    pub payload: Payload,
    pub version: Option<Bytes>,

    // BEP 42 DHT Security Extension
    pub ip: Option<Requestor>,

    pub extra: Value,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Payload {
    Query(Query),
    Response(Response),
    Error(Error),
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Query {
    Ping(Ping),
    FindNode(FindNode),
    GetPeers(GetPeers),
    AnnouncePeer(AnnouncePeer),
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Ping {
    pub id: NodeId,

    pub extra: Value,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FindNode {
    pub id: NodeId,
    pub target: NodeId,

    pub extra: Value,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct GetPeers {
    pub id: NodeId,
    pub info_hash: InfoHash,

    pub extra: Value,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AnnouncePeer {
    pub id: NodeId,
    pub implied_port: Option<bool>,
    pub info_hash: InfoHash,
    pub port: u16,
    pub token: Token,

    pub extra: Value,
}

#[bt_serde::optional]
#[derive(Clone, Debug, Deserialize, Eq, Serialize, PartialEq)]
pub struct Response {
    // `ping`, `find_node`, `get_peers`, and `announce_peer`.
    #[serde(with = "NodeIdSerdeWith")]
    pub id: NodeId,

    // `find_node` and `get_peers`.
    #[optional(with = "CompactNodeInfoListSerdeWithV4")]
    pub nodes: Option<Vec<NodeInfo>>,

    // `get_peers`.
    pub token: Option<Token>,
    #[optional(with = "CompactPeerInfoListSerdeWithV4")]
    pub values: Option<Vec<PeerInfo>>,

    #[serde(flatten)]
    pub extra: Value,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PingResponse {
    pub id: NodeId,

    pub extra: Value,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FindNodeResponse {
    pub id: NodeId,
    pub nodes: Vec<NodeInfo>,

    pub extra: Value,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct GetPeersResponse {
    pub id: NodeId,
    // BEP 5 appears to imply that the token must be present, although some DHT implementations
    // treat it as optional.
    pub token: Option<Token>,
    // BEP 5 appears to imply that values and nodes should be "either/or", but some DHT
    // implementations return both.
    pub values: Option<Vec<PeerInfo>>,
    pub nodes: Option<Vec<NodeInfo>>,

    pub extra: Value,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AnnouncePeerResponse {
    pub id: NodeId,

    pub extra: Value,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Error(i64, String);

impl Message {
    fn new(txid: Txid, payload: Payload) -> Self {
        Self {
            txid,
            payload,
            version: None,
            ip: None,
            extra: no_extra(),
        }
    }
}

impl Query {
    pub fn ping(id: NodeId) -> Message {
        Self::message(Self::Ping(Ping {
            id,
            extra: no_extra(),
        }))
    }

    pub fn find_node(id: NodeId, target: NodeId) -> Message {
        Self::message(Self::FindNode(FindNode {
            id,
            target,
            extra: no_extra(),
        }))
    }

    pub fn get_peers(id: NodeId, info_hash: InfoHash) -> Message {
        Self::message(Self::GetPeers(GetPeers {
            id,
            info_hash,
            extra: no_extra(),
        }))
    }

    pub fn announce_peer(
        id: NodeId,
        implied_port: Option<bool>,
        info_hash: InfoHash,
        port: u16,
        token: Token,
    ) -> Message {
        Self::message(Self::AnnouncePeer(AnnouncePeer {
            id,
            implied_port,
            info_hash,
            port,
            token,
            extra: no_extra(),
        }))
    }

    fn message(query: Self) -> Message {
        Message::new(random_txid(), Payload::Query(query))
    }

    pub fn id(&self) -> NodeId {
        match self {
            Self::Ping(Ping { id, .. })
            | Self::FindNode(FindNode { id, .. })
            | Self::GetPeers(GetPeers { id, .. })
            | Self::AnnouncePeer(AnnouncePeer { id, .. }) => id.clone(),
        }
    }
}

fn random_txid() -> Txid {
    // BEP 5 recommends using a 2-byte transaction id.
    Txid::copy_from_slice(&rand::random::<[u8; 2]>())
}

impl Response {
    pub fn ping(txid: Txid, id: NodeId) -> Message {
        Self::message(
            txid,
            Self {
                id,
                nodes: None,
                token: None,
                values: None,
                extra: no_extra(),
            },
        )
    }

    pub fn find_node(txid: Txid, id: NodeId, nodes: Vec<NodeInfo>) -> Message {
        Self::message(
            txid,
            Self {
                id,
                nodes: Some(nodes),
                token: None,
                values: None,
                extra: no_extra(),
            },
        )
    }

    pub fn get_peers(
        txid: Txid,
        id: NodeId,
        token: Token,
        values: Option<Vec<PeerInfo>>,
        nodes: Option<Vec<NodeInfo>>,
    ) -> Message {
        Self::message(
            txid,
            Self {
                id,
                nodes,
                token: Some(token),
                values,
                extra: no_extra(),
            },
        )
    }

    pub fn announce_peer(txid: Txid, id: NodeId) -> Message {
        Self::message(
            txid,
            Self {
                id,
                nodes: None,
                token: None,
                values: None,
                extra: no_extra(),
            },
        )
    }

    fn message(txid: Txid, response: Self) -> Message {
        Message::new(txid, Payload::Response(response))
    }
}

impl Error {
    pub fn generic(txid: Txid) -> Message {
        Self::message(txid, 201, "generic error")
    }

    pub fn server(txid: Txid) -> Message {
        Self::message(txid, 202, "server error")
    }

    pub fn protocol(txid: Txid) -> Message {
        Self::message(txid, 203, "protocol error")
    }

    pub fn method_unknown(txid: Txid) -> Message {
        Self::message(txid, 204, "method unknown")
    }

    fn message(txid: Txid, code: i64, message: &str) -> Message {
        Message::new(txid, Payload::Error(Self(code, message.to_string())))
    }
}

fn no_extra() -> Value {
    Value::Dictionary([].into())
}

const NODES: &[u8] = b"nodes";
const TOKEN: &[u8] = b"token";
const VALUES: &[u8] = b"values";

impl From<Response> for PingResponse {
    fn from(response: Response) -> Self {
        let Response {
            id,
            nodes,
            token,
            values,
            mut extra,
        } = response;
        reinsert(&mut extra, NODES, nodes);
        reinsert(&mut extra, TOKEN, token);
        reinsert(&mut extra, VALUES, values);
        Self { id, extra }
    }
}

impl TryFrom<Response> for FindNodeResponse {
    type Error = Response;

    fn try_from(response: Response) -> Result<Self, Self::Error> {
        let Response {
            id,
            nodes: Some(nodes),
            token,
            values,
            mut extra,
        } = response
        else {
            return Err(response);
        };
        reinsert(&mut extra, TOKEN, token);
        reinsert(&mut extra, VALUES, values);
        Ok(Self { id, nodes, extra })
    }
}

impl From<Response> for GetPeersResponse {
    fn from(response: Response) -> Self {
        let Response {
            id,
            nodes,
            token,
            values,
            extra,
        } = response;
        Self {
            id,
            token,
            values,
            nodes,
            extra,
        }
    }
}

impl From<Response> for AnnouncePeerResponse {
    fn from(response: Response) -> Self {
        let Response {
            id,
            nodes,
            token,
            values,
            mut extra,
        } = response;
        reinsert(&mut extra, NODES, nodes);
        reinsert(&mut extra, TOKEN, token);
        reinsert(&mut extra, VALUES, values);
        Self { id, extra }
    }
}

#[cfg(test)]
mod tests {
    use std::fmt;

    use serde::de::DeserializeOwned;

    use bt_bencode::{Value, bencode};

    use super::*;

    macro_rules! replace {
        ($new:expr => $($field:ident : $value:expr),* $(,)?) => {{
            let mut instance = $new;
            $(instance.$field = $value;)*
            instance
        }};
    }

    fn test<T>(testdata: T, expect: Value)
    where
        T: DeserializeOwned + Serialize,
        T: fmt::Debug + PartialEq,
    {
        assert_eq!(bt_bencode::to_value(&testdata), Ok(expect.clone()));
        assert_eq!(bt_bencode::from_value(expect), Ok(testdata));
    }

    #[test]
    fn query() {
        let txid = Txid::from_static(&[0x12, 0x34]);
        let one = [1u8; 20];
        let two = [2u8; 20];
        test(
            replace!(Query::ping(one.into()) => txid: txid.clone()),
            bencode!({
                b"t": txid.clone(),
                b"y": b"q",
                b"q": b"ping",
                b"a": {
                    b"id": one,
                },
            }),
        );
        test(
            replace!(Query::find_node(one.into(), two.into()) => txid: txid.clone()),
            bencode!({
                b"t": txid.clone(),
                b"y": b"q",
                b"q": b"find_node",
                b"a": {
                    b"id": one,
                    b"target": two,
                },
            }),
        );
        test(
            replace!(Query::get_peers(one.into(), two.into()) => txid: txid.clone()),
            bencode!({
                b"t": txid.clone(),
                b"y": b"q",
                b"q": b"get_peers",
                b"a": {
                    b"id": one,
                    b"info_hash": two,
                },
            }),
        );
        test(
            replace!(
                Query::announce_peer(
                    one.into(),
                    Some(true),
                    two.into(),
                    0x8001,
                    Bytes::from_static(b"foo"),
                ) =>
                txid: txid.clone(),
            ),
            bencode!({
                b"t": txid.clone(),
                b"y": b"q",
                b"q": b"announce_peer",
                b"a": {
                    b"id": one,
                    b"implied_port": 1,
                    b"info_hash": two,
                    b"port": 0x8001,
                    b"token": b"foo",
                },
            }),
        );
    }

    #[test]
    fn response() {
        let txid = Txid::from_static(&[0x12, 0x34]);
        let one = [1u8; 20];
        let two = [2u8; 20];
        let three = [3u8; 20];

        let node_info_list = vec![
            NodeInfo {
                id: one.into(),
                endpoint: "127.0.0.1:8001".parse().unwrap(),
            },
            NodeInfo {
                id: two.into(),
                endpoint: "127.0.0.2:8002".parse().unwrap(),
            },
        ];
        let mut compact_node_info_list = Vec::new();
        compact_node_info_list.extend_from_slice(&one);
        compact_node_info_list.extend_from_slice(b"\x7f\x00\x00\x01\x1f\x41");
        compact_node_info_list.extend_from_slice(&two);
        compact_node_info_list.extend_from_slice(b"\x7f\x00\x00\x02\x1f\x42");

        test(
            Response::ping(txid.clone(), one.into()),
            bencode!({
                b"t": txid.clone(),
                b"y": b"r",
                b"r": {
                    b"id": one,
                },
            }),
        );
        test(
            Response::find_node(txid.clone(), three.into(), node_info_list.clone()),
            bencode!({
                b"t": txid.clone(),
                b"y": b"r",
                b"r": {
                    b"id": three,
                    b"nodes": compact_node_info_list.clone(),
                },
            }),
        );
        test(
            Response::get_peers(
                txid.clone(),
                three.into(),
                Bytes::from_static(b"foo"),
                Some(vec![
                    "127.0.0.1:8001".parse().unwrap(),
                    "127.0.0.2:8002".parse().unwrap(),
                ]),
                Some(node_info_list.clone()),
            ),
            bencode!({
                b"t": txid.clone(),
                b"y": b"r",
                b"r": {
                    b"id": three,
                    b"token": b"foo",
                    b"values": [
                        b"\x7f\x00\x00\x01\x1f\x41",
                        b"\x7f\x00\x00\x02\x1f\x42",
                    ],
                    b"nodes": compact_node_info_list.clone(),
                },
            }),
        );
        test(
            Response::announce_peer(txid.clone(), one.into()),
            bencode!({
                b"t": txid.clone(),
                b"y": b"r",
                b"r": {
                    b"id": one,
                },
            }),
        );
    }

    #[test]
    fn error() {
        let txid = Txid::from_static(&[0x12, 0x34]);
        test(
            Error::generic(txid.clone()),
            bencode!({
                b"t": txid.clone(),
                b"y": b"e",
                b"e": [201, b"generic error"],
            }),
        );
        test(
            Error::server(txid.clone()),
            bencode!({
                b"t": txid.clone(),
                b"y": b"e",
                b"e": [202, b"server error"],
            }),
        );
        test(
            Error::protocol(txid.clone()),
            bencode!({
                b"t": txid.clone(),
                b"y": b"e",
                b"e": [203, b"protocol error"],
            }),
        );
        test(
            Error::method_unknown(txid.clone()),
            bencode!({
                b"t": txid.clone(),
                b"y": b"e",
                b"e": [204, b"method unknown"],
            }),
        );
    }

    #[test]
    fn test_reinsert() {
        let txid = Txid::from_static(&[0x12, 0x34]);

        let one = [1u8; 20];
        let two = [2u8; 20];
        let three = [3u8; 20];
        let four = [4u8; 20];

        let version = Bytes::from_static(b"0.1.2");
        let ip = "127.0.0.1:8003".parse().unwrap();

        let node_info_list = vec![
            NodeInfo {
                id: one.into(),
                endpoint: "127.0.0.1:8001".parse().unwrap(),
            },
            NodeInfo {
                id: two.into(),
                endpoint: "127.0.0.2:8002".parse().unwrap(),
            },
        ];
        let mut compact_node_info_list = Vec::new();
        compact_node_info_list.extend_from_slice(&one);
        compact_node_info_list.extend_from_slice(b"\x7f\x00\x00\x01\x1f\x41");
        compact_node_info_list.extend_from_slice(&two);
        compact_node_info_list.extend_from_slice(b"\x7f\x00\x00\x02\x1f\x42");

        let a = bencode!({
            b"id": one,
            b"target": two,
            b"info_hash": three,
            b"implied_port": 0,
            b"port": 0x8002,
            b"token": b"foo",
            b"spam": b"egg",
        });

        let r = bencode!({
            b"id": four,
            b"nodes": compact_node_info_list.clone(),
            b"token": b"bar",
            b"values": [
                b"\x7f\x00\x00\x01\x1f\x41",
                b"\x7f\x00\x00\x02\x1f\x42",
            ],
            b"hello": b"world",
        });

        let expect = bencode!({
            b"t": txid.clone(),
            b"q": b"ping",
            b"a": a.clone(),
            b"r": r.clone(),
            b"e": [301, b"other error"],
            b"v": version.clone(),
            b"ip": b"\x7f\x00\x00\x01\x1f\x43",
            b"x": b"y",
        });

        let mut copy = expect.clone();
        copy.as_dictionary_mut()
            .expect("dictionary")
            .insert(Bytes::from_static(b"y"), bencode!(b"q"));
        test(
            Message {
                txid: txid.clone(),
                payload: Payload::Query(Query::Ping(Ping {
                    id: one.into(),
                    extra: bencode!({
                        b"target": two,
                        b"info_hash": three,
                        b"implied_port": 0,
                        b"port": 0x8002,
                        b"token": b"foo",
                        b"spam": b"egg",
                    }),
                })),
                version: Some(version.clone()),
                ip: Some(ip),
                extra: bencode!({
                    b"r": r.clone(),
                    b"e": [301, b"other error"],
                    b"x": b"y",
                }),
            },
            copy,
        );

        let mut copy = expect.clone();
        copy.as_dictionary_mut()
            .expect("dictionary")
            .insert(Bytes::from_static(b"y"), bencode!(b"r"));
        test(
            Message {
                txid: txid.clone(),
                payload: Payload::Response(Response {
                    id: four.into(),
                    nodes: Some(node_info_list.clone()),
                    token: Some(Token::from_static(b"bar")),
                    values: Some(vec![
                        "127.0.0.1:8001".parse().unwrap(),
                        "127.0.0.2:8002".parse().unwrap(),
                    ]),
                    extra: bencode!({
                        b"hello": b"world",
                    }),
                }),
                version: Some(version.clone()),
                ip: Some(ip),
                extra: bencode!({
                    b"q": b"ping",
                    b"a": a.clone(),
                    b"e": [301, b"other error"],
                    b"x": b"y",
                }),
            },
            copy,
        );

        let mut copy = expect.clone();
        copy.as_dictionary_mut()
            .expect("dictionary")
            .insert(Bytes::from_static(b"y"), bencode!(b"e"));
        test(
            Message {
                txid: txid.clone(),
                payload: Payload::Error(Error(301, "other error".to_string())),
                version: Some(version.clone()),
                ip: Some(ip),
                extra: bencode!({
                    b"q": b"ping",
                    b"a": a.clone(),
                    b"r": r.clone(),
                    b"x": b"y",
                }),
            },
            copy,
        );
    }
}
