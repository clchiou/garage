// TODO: For now, we manually translate the [proto] [file] to [json].
//
// [proto]: https://github.com/etcd-io/etcd/blob/main/api/etcdserverpb/rpc.proto
// [file]: https://github.com/etcd-io/etcd/blob/main/api/mvccpb/kv.proto
// [json]: https://protobuf.dev/programming-guides/proto3/#json

use serde::{Deserialize, Serialize};
use serde_with::{base64::Base64, serde_as, skip_serializing_none, DisplayFromStr};

use crate::{Key, Value};

//
// Implementer's Notes: `Base64` does not support (or cannot?) `&[u8]`, so there are not many
// benefits to using `g1_base::define_owner`.
//

/// JSON schema according to the [source] code.
///
/// [source]: https://github.com/grpc-ecosystem/grpc-gateway/blob/main/runtime/handler.go
#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[allow(non_camel_case_types)]
pub enum StreamResponse<T> {
    result(T),
    error(Status),
}

/// Manually translated from the [proto] file.
///
/// [proto]: https://github.com/googleapis/googleapis/blob/master/google/rpc/status.proto
#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct Status {
    pub code: i32,
    pub message: String,
    pub details: Vec<serde_json::Value>,
}

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct Header {
    #[serde_as(as = "DisplayFromStr")]
    pub cluster_id: u64,
    #[serde_as(as = "DisplayFromStr")]
    pub member_id: u64,
    #[serde_as(as = "DisplayFromStr")]
    pub revision: i64,
    #[serde_as(as = "DisplayFromStr")]
    pub raft_term: u64,
}

//
// KV
//

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct DeleteRange {
    pub header: Header,
    #[serde_as(as = "DisplayFromStr")]
    pub deleted: i64,
    pub prev_kvs: Vec<KeyValue>,
}

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct Put {
    pub header: Header,
    pub prev_kv: Option<KeyValue>,
}

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct Range {
    pub header: Header,
    pub kvs: Vec<KeyValue>,
    pub more: bool,
    #[serde_as(as = "DisplayFromStr")]
    pub count: i64,
}

//
// Watch
//

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct Watch {
    pub header: Header,
    #[serde_as(as = "DisplayFromStr")]
    pub watch_id: i64,
    pub created: bool,
    pub canceled: bool,
    #[serde_as(as = "DisplayFromStr")]
    pub compact_revision: i64,
    pub cancel_reason: String,
    pub fragment: bool,
    pub events: Vec<Event>,
}

//
// Lease
//

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct LeaseGrant {
    pub header: Header,
    #[serde_as(as = "DisplayFromStr")]
    #[serde(rename = "ID")]
    pub id: i64,
    #[serde_as(as = "DisplayFromStr")]
    #[serde(rename = "TTL")]
    pub ttl: i64,
    pub error: Option<String>,
}

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct LeaseKeepAlive {
    pub header: Header,
    #[serde_as(as = "DisplayFromStr")]
    #[serde(rename = "ID")]
    pub id: i64,
    #[serde_as(as = "Option<DisplayFromStr>")]
    #[serde(rename = "TTL")]
    pub ttl: Option<i64>,
}

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct LeaseRevoke {
    pub header: Header,
}

//
// Auth
//

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct Authenticate {
    pub header: Header,
    pub token: String,
}

//
// mvccpb/kv.proto
//

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct KeyValue {
    #[serde_as(as = "Base64")]
    pub key: Key,
    #[serde_as(as = "DisplayFromStr")]
    pub create_revision: i64,
    #[serde_as(as = "DisplayFromStr")]
    pub mod_revision: i64,
    #[serde_as(as = "DisplayFromStr")]
    pub version: i64,
    #[serde_as(as = "Base64")]
    pub value: Value,
    #[serde_as(as = "DisplayFromStr")]
    pub lease: i64,
}

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct Event {
    #[serde(rename = "type")]
    pub typ: EventType,
    pub kv: KeyValue,
    pub prev_kv: Option<KeyValue>,
}

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub enum EventType {
    #[default]
    PUT,
    DELETE,
}
