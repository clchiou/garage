use snafu::prelude::*;

use bittorrent_base::compact;
use bittorrent_bencode::{convert, dict, own};

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    #[snafu(display("all announce urls failed"))]
    AnnounceUrlsFailed,

    #[snafu(display("expect byte string: {value:?}"))]
    ExpectByteString { value: own::Value },
    #[snafu(display("expect integer: {value:?}"))]
    ExpectInteger { value: own::Value },
    #[snafu(display("expect list: {value:?}"))]
    ExpectList { value: own::Value },
    #[snafu(display("expect dict: {value:?}"))]
    ExpectDictionary { value: own::Value },
    #[snafu(display("invalid utf8 string: \"{string}\""))]
    InvalidUtf8String { string: String },

    #[snafu(display("missing dictionary key: \"{key}\""))]
    MissingDictionaryKey { key: String },

    #[snafu(display("expect compact size == {expect}: {size}"))]
    ExpectCompactSize { size: usize, expect: usize },
    #[snafu(display("expect compact array size % {unit_size} == 0: {size}"))]
    ExpectCompactArraySize { size: usize, unit_size: usize },

    #[snafu(display("tracker failure: {reason}"))]
    Failure { reason: String },
    #[snafu(display("invalid interval: {interval}"))]
    InvalidInterval { interval: i64 },
    #[snafu(display("invalid num_peers: {num_peers}"))]
    InvalidNumPeers { num_peers: i64 },
    #[snafu(display("invalid peer_id: {peer_id}"))]
    InvalidPeerId { peer_id: String },
    #[snafu(display("invalid peer list: {peers:?}"))]
    InvalidPeerList { peers: own::Value },
    #[snafu(display("invalid port: {port}"))]
    InvalidPort { port: i64 },
}

impl From<convert::Error> for Error {
    fn from(error: convert::Error) -> Self {
        match error {
            convert::Error::ExpectByteString { value } => Self::ExpectByteString { value },
            convert::Error::ExpectInteger { value } => Self::ExpectInteger { value },
            convert::Error::ExpectList { value } => Self::ExpectList { value },
            convert::Error::ExpectDictionary { value } => Self::ExpectDictionary { value },
            convert::Error::InvalidUtf8String { string } => Self::InvalidUtf8String { string },
        }
    }
}

impl From<dict::Error> for Error {
    fn from(error: dict::Error) -> Self {
        match error {
            dict::Error::MissingDictionaryKey { key } => Error::MissingDictionaryKey { key },
        }
    }
}

impl From<compact::Error> for Error {
    fn from(error: compact::Error) -> Self {
        match error {
            compact::Error::ExpectSize { size, expect } => {
                Error::ExpectCompactSize { size, expect }
            }
            compact::Error::ExpectArraySize { size, unit_size } => {
                Error::ExpectCompactArraySize { size, unit_size }
            }
        }
    }
}
