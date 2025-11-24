// TODO: For now, we manually translate the [proto] file to [json].
//
// [proto]: https://github.com/etcd-io/etcd/blob/main/api/etcdserverpb/rpc.proto
// [json]: https://protobuf.dev/programming-guides/proto3/#json

use serde::{Deserialize, Serialize};
use serde_with::{DisplayFromStr, base64::Base64, serde_as, skip_serializing_none};

use crate::private::{Request, StreamRequest};
use crate::response;
use crate::{Key, Value};

//
// Implementer's Notes: `Base64` does not support (or cannot?) `&[u8]`, so there are not many
// benefits to using `g1_base::define_owner`.
//

macro_rules! impl_request {
    ($name:ident, $endpoint:tt $(,)?) => {
        impl Request for $name {
            const ENDPOINT: &'static str = $endpoint;

            type Response = response::$name;
        }
    };
}

//
// KV
//

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct DeleteRange {
    #[serde_as(as = "Base64")]
    pub key: Key,
    #[serde_as(as = "Base64")]
    pub range_end: Key,
    pub prev_kv: bool,
}

impl_request!(DeleteRange, "v3/kv/deleterange");

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct Put {
    #[serde_as(as = "Base64")]
    pub key: Key,
    #[serde_as(as = "Base64")]
    pub value: Value,
    #[serde_as(as = "DisplayFromStr")]
    pub lease: i64,
    pub prev_kv: bool,
    pub ignore_value: bool,
    pub ignore_lease: bool,
}

impl_request!(Put, "v3/kv/put");

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct Range {
    #[serde_as(as = "Base64")]
    pub key: Key,
    #[serde_as(as = "Base64")]
    pub range_end: Key,
    #[serde_as(as = "DisplayFromStr")]
    pub limit: i64,
    #[serde_as(as = "DisplayFromStr")]
    pub revision: i64,
    pub sort_order: SortOrder,
    pub sort_target: SortTarget,
    pub serializable: bool,
    pub keys_only: bool,
    pub count_only: bool,
    #[serde_as(as = "DisplayFromStr")]
    pub min_mod_revision: i64,
    #[serde_as(as = "DisplayFromStr")]
    pub max_mod_revision: i64,
    #[serde_as(as = "DisplayFromStr")]
    pub min_create_revision: i64,
    #[serde_as(as = "DisplayFromStr")]
    pub max_create_revision: i64,
}

impl_request!(Range, "v3/kv/range");

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub enum SortOrder {
    #[default]
    NONE,
    ASCEND,
    DESCEND,
}

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub enum SortTarget {
    #[default]
    KEY,
    VERSION,
    CREATE,
    MOD,
    VALUE,
}

//
// Txn
//

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct Txn {
    pub compare: Vec<Compare>,
    pub success: Vec<RequestOp>,
    pub failure: Vec<RequestOp>,
}

impl_request!(Txn, "v3/kv/txn");

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct Compare {
    pub result: CompareResult,
    pub target: CompareTarget,
    #[serde_as(as = "Base64")]
    pub key: Key,
    #[serde(flatten)]
    pub target_union: TargetUnion,
    #[serde_as(as = "Base64")]
    pub range_end: Key,
}

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub enum CompareResult {
    #[default]
    EQUAL,
    GREATER,
    LESS,
    #[allow(non_camel_case_types)]
    NOT_EQUAL,
}

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub enum CompareTarget {
    #[default]
    VERSION,
    CREATE,
    MOD,
    VALUE,
    LEASE,
}

#[allow(non_camel_case_types)]
#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum TargetUnion {
    version(#[serde_as(as = "DisplayFromStr")] i64),
    create_revision(#[serde_as(as = "DisplayFromStr")] i64),
    mod_revision(#[serde_as(as = "DisplayFromStr")] i64),
    value(#[serde_as(as = "Base64")] Value),
    lease(#[serde_as(as = "DisplayFromStr")] i64),
}

impl Default for TargetUnion {
    fn default() -> Self {
        Self::version(0)
    }
}

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum RequestOp {
    #[serde(rename = "request_range")]
    Range(Range),
    #[serde(rename = "request_put")]
    Put(Put),
    #[serde(rename = "request_delete_range")]
    DeleteRange(DeleteRange),
    #[serde(rename = "request_txn")]
    Txn(Txn),
}

//
// Watch
//

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum Watch {
    #[serde(rename = "create_request")]
    Create(WatchCreate),
}

impl_request!(Watch, "v3/watch");
impl StreamRequest for Watch {}

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct WatchCreate {
    #[serde_as(as = "Base64")]
    pub key: Key,
    #[serde_as(as = "Base64")]
    pub range_end: Key,
    #[serde_as(as = "DisplayFromStr")]
    pub start_revision: i64,
    pub progress_notify: bool,
    pub filters: Vec<FilterType>,
    pub prev_kv: bool,
    #[serde_as(as = "DisplayFromStr")]
    pub watch_id: i64,
    pub fragment: bool,
}

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub enum FilterType {
    #[default]
    NOPUT,
    NODELETE,
}

//
// Lease
//

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct LeaseGrant {
    #[serde_as(as = "DisplayFromStr")]
    #[serde(rename = "TTL")]
    pub ttl: i64,
    #[serde_as(as = "DisplayFromStr")]
    #[serde(rename = "ID")]
    pub id: i64,
}

impl_request!(LeaseGrant, "v3/lease/grant");

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct LeaseKeepAlive {
    #[serde_as(as = "DisplayFromStr")]
    #[serde(rename = "ID")]
    pub id: i64,
}

impl_request!(LeaseKeepAlive, "v3/lease/keepalive");
impl StreamRequest for LeaseKeepAlive {}

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct LeaseRevoke {
    #[serde_as(as = "DisplayFromStr")]
    #[serde(rename = "ID")]
    pub id: i64,
}

impl_request!(LeaseRevoke, "v3/lease/revoke");

//
// Auth
//

#[serde_as]
#[skip_serializing_none]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(default)]
pub struct Authenticate {
    pub name: String,
    pub password: String,
}

impl_request!(Authenticate, "v3/auth/authenticate");
