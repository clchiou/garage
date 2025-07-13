use bytes::Bytes;
use serde::{Deserialize, Serialize};

use bt_base::{InfoHash, NodeId};
use bt_bencode::Value;
use bt_serde::SerdeWith;

use crate::info_hash::InfoHashSerdeWith;
use crate::node_id::NodeIdSerdeWith;
use crate::reinsert::{ToValue, reinsert};
use crate::requestor::{CompactRequestorSerdeWith, Requestor};
use crate::{
    AnnouncePeer, Error, FindNode, GetPeers, Message, Payload, Ping, Query, Response, Token,
};

//
// We introduce an intermediate type, `FlatMessage`, in the de/serialization of `Message`.
// `FlatMessage` more closely matches the KRPC message layout as specified in BEP 5, and deriving
// `De/Serialize` for it is relatively straightforward.  In contrast, `Message`, while more
// idiomatic in Rust, has to be annotated with the `serde(flatten)` to be derived correctly.
// However, using multiple `serde(flatten)` leads to problematic behavior.
//
// Also note that `bt_bencode` does not support the deserialization of non-default enum
// representations.
//
#[bt_serde::optional]
#[derive(Deserialize, Serialize)]
pub(crate) struct FlatMessage {
    #[serde(rename = "t")]
    txid: Bytes,

    #[serde(rename = "y")]
    type_: FlatType,

    #[serde(rename = "q")]
    query: Option<FlatQuery>,
    #[serde(rename = "a")]
    args: Option<FlatArgs>,

    #[serde(rename = "r")]
    response: Option<Response>,

    #[serde(rename = "e")]
    error: Option<Error>,

    #[serde(rename = "v")]
    version: Option<Bytes>,

    #[optional(with = "CompactRequestorSerdeWith")]
    ip: Option<Requestor>,

    #[serde(flatten)]
    extra: Value,
}

#[derive(Deserialize, Serialize)]
enum FlatType {
    #[serde(rename = "q")]
    Query,
    #[serde(rename = "r")]
    Response,
    #[serde(rename = "e")]
    Error,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum FlatQuery {
    Ping,
    FindNode,
    GetPeers,
    AnnouncePeer,
}

#[bt_serde::optional]
#[derive(Deserialize, Serialize)]
struct FlatArgs {
    // `ping`, `find_node`, `get_peers`, and `announce_peer`.
    #[serde(with = "NodeIdSerdeWith")]
    id: NodeId,

    // `find_node`.
    #[optional(with = "NodeIdSerdeWith")]
    target: Option<NodeId>,

    // `get_peers` and `announce_peer`.
    #[optional(with = "InfoHashSerdeWith")]
    info_hash: Option<InfoHash>,

    // `announce_peer`.
    implied_port: Option<bool>,
    port: Option<u16>,
    token: Option<Token>,

    #[serde(flatten)]
    extra: Value,
}

const QUERY: &[u8] = b"q";
const ARGS: &[u8] = b"a";
const RESPONSE: &[u8] = b"r";
const ERROR: &[u8] = b"e";

impl TryFrom<FlatMessage> for Message {
    type Error = &'static str;

    fn try_from(flat: FlatMessage) -> Result<Self, Self::Error> {
        let FlatMessage {
            txid,
            type_,
            query,
            args,
            response,
            error,
            version,
            ip,
            mut extra,
        } = flat;
        let payload = match type_ {
            FlatType::Query => {
                reinsert(&mut extra, RESPONSE, response);
                reinsert(&mut extra, ERROR, error);
                Payload::Query(Query::try_from((
                    query.ok_or("expect `q`")?,
                    args.ok_or("expect `a`")?,
                ))?)
            }
            FlatType::Response => {
                reinsert(&mut extra, QUERY, query);
                reinsert(&mut extra, ARGS, args);
                reinsert(&mut extra, ERROR, error);
                Payload::Response(response.ok_or("expect `r`")?)
            }
            FlatType::Error => {
                reinsert(&mut extra, QUERY, query);
                reinsert(&mut extra, ARGS, args);
                reinsert(&mut extra, RESPONSE, response);
                Payload::Error(error.ok_or("expect `e`")?)
            }
        };
        Ok(Self {
            txid,
            payload,
            version,
            ip,
            extra,
        })
    }
}

impl From<Message> for FlatMessage {
    fn from(message: Message) -> Self {
        let Message {
            txid,
            payload,
            version,
            ip,
            extra,
        } = message;
        let (type_, query, args, response, error) = match payload {
            Payload::Query(query) => {
                let (query, args) = query.into();
                (FlatType::Query, Some(query), Some(args), None, None)
            }
            Payload::Response(response) => (FlatType::Response, None, None, Some(response), None),
            Payload::Error(error) => (FlatType::Error, None, None, None, Some(error)),
        };
        Self {
            txid,
            type_,
            query,
            args,
            response,
            error,
            version,
            ip,
            extra,
        }
    }
}

const TARGET: &[u8] = b"target";
const INFO_HASH: &[u8] = b"info_hash";
const IMPLIED_PORT: &[u8] = b"implied_port";
const PORT: &[u8] = b"port";
const TOKEN: &[u8] = b"token";

impl TryFrom<(FlatQuery, FlatArgs)> for Query {
    type Error = &'static str;

    fn try_from((query, args): (FlatQuery, FlatArgs)) -> Result<Self, Self::Error> {
        let FlatArgs {
            id,
            target,
            info_hash,
            implied_port,
            port,
            token,
            mut extra,
        } = args;
        match query {
            FlatQuery::Ping => {
                reinsert(&mut extra, TARGET, target);
                reinsert(&mut extra, INFO_HASH, info_hash);
                reinsert(&mut extra, IMPLIED_PORT, implied_port);
                reinsert(&mut extra, PORT, port);
                reinsert(&mut extra, TOKEN, token);
                Ok(Self::Ping(Ping { id, extra }))
            }
            FlatQuery::FindNode => {
                reinsert(&mut extra, INFO_HASH, info_hash);
                reinsert(&mut extra, IMPLIED_PORT, implied_port);
                reinsert(&mut extra, PORT, port);
                reinsert(&mut extra, TOKEN, token);
                Ok(Self::FindNode(FindNode {
                    id,
                    target: target.ok_or("expect `target`")?,
                    extra,
                }))
            }
            FlatQuery::GetPeers => {
                reinsert(&mut extra, TARGET, target);
                reinsert(&mut extra, IMPLIED_PORT, implied_port);
                reinsert(&mut extra, PORT, port);
                reinsert(&mut extra, TOKEN, token);
                Ok(Self::GetPeers(GetPeers {
                    id,
                    info_hash: info_hash.ok_or("expect `info_hash`")?,
                    extra,
                }))
            }
            FlatQuery::AnnouncePeer => {
                reinsert(&mut extra, TARGET, target);
                Ok(Self::AnnouncePeer(AnnouncePeer {
                    id,
                    implied_port,
                    info_hash: info_hash.ok_or("expect `info_hash`")?,
                    port: port.ok_or("expect `port`")?,
                    token: token.ok_or("expect `token`")?,
                    extra,
                }))
            }
        }
    }
}

impl From<Query> for (FlatQuery, FlatArgs) {
    fn from(query: Query) -> Self {
        match query {
            Query::Ping(Ping { id, extra }) => (
                FlatQuery::Ping,
                FlatArgs {
                    id,
                    target: None,
                    info_hash: None,
                    implied_port: None,
                    port: None,
                    token: None,
                    extra,
                },
            ),
            Query::FindNode(FindNode { id, target, extra }) => (
                FlatQuery::FindNode,
                FlatArgs {
                    id,
                    target: Some(target),
                    info_hash: None,
                    implied_port: None,
                    port: None,
                    token: None,
                    extra,
                },
            ),
            Query::GetPeers(GetPeers {
                id,
                info_hash,
                extra,
            }) => (
                FlatQuery::GetPeers,
                FlatArgs {
                    id,
                    target: None,
                    info_hash: Some(info_hash),
                    implied_port: None,
                    port: None,
                    token: None,
                    extra,
                },
            ),
            Query::AnnouncePeer(AnnouncePeer {
                id,
                implied_port,
                info_hash,
                port,
                token,
                extra,
            }) => (
                FlatQuery::AnnouncePeer,
                FlatArgs {
                    id,
                    target: None,
                    info_hash: Some(info_hash),
                    implied_port,
                    port: Some(port),
                    token: Some(token),
                    extra,
                },
            ),
        }
    }
}

impl ToValue for FlatQuery {
    fn to_value(self) -> Value {
        bt_bencode::to_value(&self).expect("to_value")
    }
}

impl ToValue for FlatArgs {
    fn to_value(self) -> Value {
        bt_bencode::to_value(&self).expect("to_value")
    }
}

impl ToValue for Response {
    fn to_value(self) -> Value {
        bt_bencode::to_value(&self).expect("to_value")
    }
}

impl ToValue for Error {
    fn to_value(self) -> Value {
        bt_bencode::to_value(&self).expect("to_value")
    }
}
