#![feature(iterator_try_collect)]

mod sanity;
mod serde_impl;

use std::collections::BTreeMap;
use std::fmt;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_bytes::Bytes;
use sha1::{Digest, Sha1};
use snafu::Snafu;

use g1_base::{
    cmp::PartialEqExt,
    fmt::{DebugExt, Hex},
};

use bittorrent_base::INFO_HASH_SIZE;
use bittorrent_bencode::{borrow, own, FormatDictionary};

pub use self::sanity::Insanity;

#[derive(Clone, DebugExt, Deserialize, Eq, PartialEq, Serialize)]
// Use two-pass (de-)serialization because:
// * `bittorrent_bencode::serde` does not map a `None`-valued field to "not present" in the output
//   dictionary.
// * The keys in the metainfo dictionary are inconsistent; they are neither in "snake_case" nor
//   "kebab-case" format.
#[serde(
    try_from = "BTreeMap<&[u8], borrow::Value>",
    into = "BTreeMap<&Bytes, own::Value>"
)]
pub struct Metainfo<'a> {
    pub announce: Option<&'a str>,
    // BEP 12 Multitracker Metadata Extension
    pub announce_list: Option<Vec<Vec<&'a str>>>,
    // BEP 5 DHT Protocol
    pub nodes: Option<Vec<(&'a str, u16)>>,
    // BEP 19 WebSeed - HTTP/FTP Seeding (GetRight style)
    pub url_list: Option<Vec<&'a str>>,

    pub comment: Option<&'a str>,
    pub created_by: Option<&'a str>,
    pub creation_date: Option<DateTime<Utc>>,
    pub encoding: Option<&'a str>,
    pub info: Info<'a>,

    #[debug(with = FormatDictionary)]
    pub extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Clone, DebugExt, Eq, PartialEqExt)]
pub struct Info<'a> {
    #[debug(skip)]
    #[partial_eq(skip)]
    pub raw_info: &'a [u8],

    pub name: &'a str,
    pub mode: Mode<'a>,
    pub piece_length: u64,
    #[debug(with = FormatPieces)]
    pub pieces: Vec<&'a [u8]>,
    // BEP 27 Private Torrents
    pub private: Option<bool>,

    #[debug(with = FormatDictionary)]
    pub extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Mode<'a> {
    SingleFile {
        length: u64,
        md5sum: Option<&'a str>,
    },
    MultiFile {
        files: Vec<File<'a>>,
    },
}

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub struct File<'a> {
    pub path: Vec<&'a str>,
    pub length: u64,
    pub md5sum: Option<&'a str>,

    #[debug(with = FormatDictionary)]
    pub extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Error {
    #[snafu(display("expect byte string: {value:?}"))]
    ExpectByteString { value: own::Value },
    #[snafu(display("expect integer: {value:?}"))]
    ExpectInteger { value: own::Value },
    #[snafu(display("expect list: {value:?}"))]
    ExpectList { value: own::Value },
    #[snafu(display("expect dict: {value:?}"))]
    ExpectDictionary { value: own::Value },

    #[snafu(display("invalid length: {length}"))]
    InvalidLength { length: i64 },
    #[snafu(display("invalid node: {node:?}"))]
    InvalidNode { node: Vec<own::Value> },
    #[snafu(display("invalid piece hash size: {size}"))]
    InvalidPieceHashSize { size: usize },
    #[snafu(display("invalid port: {port}"))]
    InvalidPort { port: i64 },
    #[snafu(display("invalid timestamp: {timestamp}"))]
    InvalidTimestamp { timestamp: i64 },
    #[snafu(display("invalid utf8 string: \"{string}\""))]
    InvalidUtf8String { string: String },

    #[snafu(display("missing dictionary key: \"{key}\""))]
    MissingDictionaryKey { key: String },

    #[snafu(display("insane: {symptoms:?}"))]
    Insane { symptoms: Vec<Insanity> },
}

impl<'a> Info<'a> {
    pub fn compute_info_hash(&self) -> [u8; INFO_HASH_SIZE] {
        Sha1::digest(self.raw_info).into()
    }

    pub fn length(&self) -> u64 {
        match &self.mode {
            Mode::SingleFile { length, .. } => *length,
            Mode::MultiFile { files } => files.iter().map(|f| f.length).sum(),
        }
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl<'a> Metainfo<'a> {
        pub fn new_dummy() -> Self {
            Self {
                announce: None,
                announce_list: None,
                nodes: None,
                url_list: None,
                comment: None,
                created_by: None,
                creation_date: None,
                encoding: None,
                info: Info::new_dummy(),
                extra: BTreeMap::new(),
            }
        }
    }

    impl<'a> Info<'a> {
        pub fn new_dummy() -> Self {
            Self {
                raw_info: b"".as_slice(),
                name: "",
                mode: Mode::SingleFile {
                    length: 0,
                    md5sum: None,
                },
                piece_length: 0,
                pieces: vec![],
                private: None,
                extra: BTreeMap::new(),
            }
        }
    }

    impl<'a> File<'a> {
        pub fn new_dummy() -> Self {
            Self {
                path: vec![],
                length: 0,
                md5sum: None,
                extra: BTreeMap::new(),
            }
        }
    }
}

struct FormatPieces<'a>(&'a Vec<&'a [u8]>);

impl<'a> fmt::Debug for FormatPieces<'a> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_list()
            .entries(self.0.iter().copied().map(Hex))
            .finish()
    }
}
