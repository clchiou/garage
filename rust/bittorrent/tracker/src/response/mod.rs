mod serde_impl;

use std::collections::BTreeMap;
use std::net::SocketAddr;
use std::time::Duration;

use serde::Deserialize;

use g1_base::fmt::{DebugExt, EscapeAscii};

use bittorrent_bencode::{FormatDictionary, borrow};

g1_base::define_owner!(#[derive(Debug)] pub ResponseOwner for Response);

// Implementer's Notes:
// * For the ease of implementation, we employ a two-pass (de-)serialization approach.
// * For now, we do not implement `Serialize`.
#[derive(Clone, DebugExt, Deserialize, Eq, PartialEq)]
#[serde(try_from = "BTreeMap<&[u8], borrow::Value>")]
pub struct Response<'a> {
    pub warning_message: Option<&'a str>,
    pub interval: Duration,
    pub min_interval: Option<Duration>,
    pub tracker_id: Option<&'a str>,
    pub complete: Option<u64>,
    pub incomplete: Option<u64>,
    pub peers: Vec<PeerContactInfo<'a>>,

    #[debug(with = FormatDictionary)]
    pub extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub struct PeerContactInfo<'a> {
    #[debug(with = EscapeAscii)]
    pub id: Option<&'a [u8]>,
    pub endpoint: Endpoint<'a>,

    #[debug(with = FormatDictionary)]
    pub extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Endpoint<'a> {
    SocketAddr(SocketAddr),
    DomainName(&'a str, u16),
}

impl From<SocketAddr> for PeerContactInfo<'_> {
    fn from(endpoint: SocketAddr) -> Self {
        Self {
            id: None,
            endpoint: Endpoint::SocketAddr(endpoint),
            extra: BTreeMap::new(),
        }
    }
}
