pub(crate) mod query;
pub(crate) mod response;

mod owner_impl;
mod serde_impl;

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_bytes::Bytes;
use snafu::prelude::*;

use g1_base::fmt::{DebugExt, Hex};

use bittorrent_base::{INFO_HASH_SIZE, NODE_ID_SIZE};
use bittorrent_bencode::{borrow, own, FormatDictionary};

use self::{
    query::Query,
    response::{Error as ErrorResponse, Response},
};

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub(crate) enum Error {
    #[snafu(display("expect byte string: {value:?}"))]
    ExpectByteString { value: own::Value },
    #[snafu(display("expect integer: {value:?}"))]
    ExpectInteger { value: own::Value },
    #[snafu(display("expect list: {value:?}"))]
    ExpectList { value: own::Value },
    #[snafu(display("expect dict: {value:?}"))]
    ExpectDictionary { value: own::Value },

    // TODO: Should we use `own::Value` instead?
    #[snafu(display("expect response: {message:?}"))]
    ExpectResponse { message: String },

    #[snafu(display("invalid utf8 string: \"{string}\""))]
    InvalidUtf8String { string: String },

    #[snafu(display("missing dictionary key: \"{key}\""))]
    MissingDictionaryKey { key: String },

    //
    // `Message` and `Payload` errors.
    //
    #[snafu(display("expect txid size == {TXID_SIZE}: {txid:?}"))]
    ExpectTxidSize { txid: Vec<u8> },
    #[snafu(display("unknown message type: {message_type:?}"))]
    UnknownMessageType { message_type: Vec<u8> },

    //
    // `Query` errors.
    //
    #[snafu(display("expect id size == {NODE_ID_SIZE}: {id:?}"))]
    ExpectIdSize { id: Vec<u8> },
    #[snafu(display("expect info_hash size == {INFO_HASH_SIZE}: {info_hash:?}"))]
    ExpectInfoHashSize { info_hash: Vec<u8> },
    #[snafu(display("invalid node port: {port}"))]
    InvalidNodePort { port: i64 },
    #[snafu(display("unknown method name: {method_name:?}"))]
    UnknownMethodName { method_name: Vec<u8> },

    //
    // `Response` errors.
    //
    #[snafu(display("expect compact size == {expect}: {size}"))]
    ExpectCompactSize { size: usize, expect: usize },
    #[snafu(display("expect compact array size % {unit_size} == 0: {size}"))]
    ExpectCompactArraySize { size: usize, unit_size: usize },

    //
    // `Error` errors.
    //
    #[snafu(display("expect error list size == 2: {size}"))]
    ExpectErrorListSize { size: usize },
    #[snafu(display("unknown error code: {error_code}"))]
    UnknownErrorCode { error_code: i64 },
}

g1_base::define_owner!(#[derive(Debug)] pub(crate) MessageOwner for Message);

// Implementer's Notes: For the ease of implementation, we employ a two-pass (de-)serialization
// approach.
#[derive(Clone, DebugExt, Deserialize, Eq, PartialEq, Serialize)]
#[serde(
    try_from = "BTreeMap<&[u8], borrow::Value>",
    into = "BTreeMap<&Bytes, own::Value>"
)]
pub(crate) struct Message<'a> {
    #[debug(with = Hex)]
    pub(crate) txid: &'a [u8],
    pub(crate) payload: Payload<'a>,
    #[debug(with = Hex)]
    pub(crate) version: Option<&'a [u8]>,

    #[debug(with = FormatDictionary)]
    pub(crate) extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) enum Payload<'a> {
    Query(Query<'a>),
    Response(Response<'a>),
    Error(ErrorResponse<'a>),
}

const TXID_SIZE: usize = 2;

impl<'a> Message<'a> {
    pub(crate) fn new_txid() -> [u8; TXID_SIZE] {
        rand::random::<[u8; TXID_SIZE]>()
    }

    pub(crate) fn new(txid: &'a [u8], payload: Payload<'a>) -> Self {
        Self {
            txid,
            payload,
            version: None, // TODO: Supply the peer version, as specified in BEP 20.
            extra: BTreeMap::new(),
        }
    }
}
