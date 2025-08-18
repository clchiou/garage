#![feature(debug_closure_helpers)]

mod sanity;

use std::fmt;
use std::sync::OnceLock;

use serde::de::{Deserializer, Error as _};
use serde::ser::Serializer;
use serde::{Deserialize, Serialize};

use bt_base::layout;
use bt_base::{InfoHash, Layout, Md5Hash, PieceHashes};
use bt_bencode::{Value, WithRaw};
use bt_serde::SerdeWith;

pub use g1_chrono::{Timestamp, TimestampExt};

pub use self::sanity::{Insane, SanityCheck, Symptom};

#[bt_serde::optional]
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Metainfo {
    announce: Option<String>,

    info: WithRaw<Info>,
    #[serde(skip)]
    info_hash: OnceLock<InfoHash>,

    // BEP 12 Multitracker Metadata Extension
    #[serde(rename = "announce-list")]
    announce_list: Option<Vec<Vec<String>>>,

    // BEP 5 DHT Protocol
    nodes: Option<Vec<(String, u16)>>,

    // BEP 19 WebSeed - HTTP/FTP Seeding (GetRight style)
    #[serde(rename = "url-list")]
    url_list: Option<Vec<String>>,

    //
    // Non-BEP fields.
    //
    comment: Option<String>,

    #[serde(rename = "created by")]
    created_by: Option<String>,

    #[serde(rename = "creation date")]
    #[optional(with = "TimestampSerdeWith")]
    creation_date: Option<Timestamp>,

    encoding: Option<String>,

    #[serde(flatten)]
    extra: Value,
}

//
// We introduce an intermediate type, `FlatInfo`, in the de/serialization of `Info` and `Mode`.
// `FlatInfo` more closely matches the layout of the `info` dictionary as specified in BEP 3, and
// deriving `De/Serialize` for it is relatively straightforward.  In contrast, `Info` and `Mode`,
// while more idiomatic in Rust, have to be annotated with the `serde(flatten)` and
// `serde(untagged)` to be derived correctly.  However, using multiple `serde(flatten)` leads to
// problematic behavior.
//
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(try_from = "FlatInfo", into = "FlatInfo")]
pub struct Info {
    name: String,
    piece_length: u64,
    pieces: PieceHashes,
    mode: Mode,

    // BEP 27 Private Torrents
    private: Option<bool>,

    extra: Value,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Mode {
    Single {
        length: u64,

        //
        // Non-BEP fields.
        //
        md5sum: Option<Md5Hash>,
    },
    Multiple {
        files: Vec<File>,
    },
}

#[bt_serde::optional]
#[derive(Deserialize, Serialize)]
struct FlatInfo {
    name: String,
    #[serde(rename = "piece length")]
    piece_length: u64,
    pieces: PieceHashes,

    // Mode::Single
    length: Option<u64>,
    md5sum: Option<Md5Hash>,

    // Mode::Multiple
    files: Option<Vec<File>>,

    private: Option<bool>,

    #[serde(flatten)]
    extra: Value,
}

#[bt_serde::optional]
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct File {
    length: u64,
    path: Vec<String>,

    //
    // Non-BEP fields.
    //
    md5sum: Option<Md5Hash>,

    #[serde(flatten)]
    extra: Value,
}

impl TryFrom<FlatInfo> for Info {
    type Error = &'static str;

    fn try_from(flat: FlatInfo) -> Result<Self, Self::Error> {
        let FlatInfo {
            name,
            piece_length,
            pieces,
            length,
            md5sum,
            files,
            private,
            extra,
        } = flat;
        let mode = match (length, files) {
            (Some(length), None) => Mode::Single { length, md5sum },
            (None, Some(files)) => Mode::Multiple { files },
            _ => return Err("expect `info` to contain either `length` or `files`"),
        };
        Ok(Self {
            name,
            piece_length,
            pieces,
            mode,
            private,
            extra,
        })
    }
}

impl From<Info> for FlatInfo {
    fn from(info: Info) -> Self {
        let Info {
            name,
            piece_length,
            pieces,
            mode,
            private,
            extra,
        } = info;
        let (length, md5sum, files) = match mode {
            Mode::Single { length, md5sum } => (Some(length), md5sum, None),
            Mode::Multiple { files } => (None, None, Some(files)),
        };
        Self {
            name,
            piece_length,
            pieces,
            length,
            md5sum,
            files,
            private,
            extra,
        }
    }
}

struct TimestampSerdeWith;

impl SerdeWith for TimestampSerdeWith {
    type Value = Timestamp;

    fn deserialize<'de, D>(deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        let secs = i64::deserialize(deserializer)?;
        Timestamp::from_timestamp(secs, 0).ok_or_else(|| {
            D::Error::custom(fmt::from_fn(|f| {
                std::write!(f, "invalid timestamp: {secs}")
            }))
        })
    }

    fn serialize<S>(value: &Self::Value, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        value.timestamp().serialize(serializer)
    }
}

macro_rules! impl_getters {
    ($($name:ident . $func:ident ( $( $arg:expr $(,)? )? ) => $type:ty),* $(,)?) => {
        $(impl_getters!(@ $name, $func($($arg),*), $type);)*
    };

    (@ $name:ident, _copy(), $type:ty $(,)?) => {
        pub fn $name(&self) -> $type {
            self.$name
        }
    };

    (@ $name:ident, _ref(), $type:ty $(,)?) => {
        pub fn $name(&self) -> $type {
            &self.$name
        }
    };

    (@ $name:ident, $func:ident ( $( $arg:expr )? ), $type:ty $(,)?) => {
        pub fn $name(&self) -> $type {
            self.$name.$func($($arg),*)
        }
    };
}

impl Metainfo {
    impl_getters!(
        announce.as_deref() => Option<&str>,
        info._ref() => &Info,
        announce_list.as_deref() => Option<&[Vec<String>]>,
        nodes.as_deref() => Option<&[(String, u16)]>,
        url_list.as_deref() => Option<&[String]>,
        comment.as_deref() => Option<&str>,
        created_by.as_deref() => Option<&str>,
        creation_date._copy() => Option<Timestamp>,
        encoding.as_deref() => Option<&str>,
        extra._ref() => &Value,
    );

    pub fn info_blob(&self) -> &[u8] {
        WithRaw::as_raw(&self.info)
    }

    pub fn info_hash(&self) -> InfoHash {
        self.info_hash
            .get_or_init(|| InfoHash::digest(self.info_blob()))
            .clone()
    }
}

impl Info {
    impl_getters!(
        name.as_str() => &str,
        piece_length._copy() => u64,
        pieces.clone() => PieceHashes,
        mode._ref() => &Mode,
        private.unwrap_or(false) => bool,
        extra._ref() => &Value,
    );

    pub fn layout(&self) -> Result<Layout, layout::Error> {
        Layout::new(
            self.length(),
            self.pieces().len().try_into().expect("num_pieces"),
            self.piece_length(),
        )
    }

    pub fn length(&self) -> u64 {
        self.mode().length()
    }
}

impl Mode {
    pub fn length(&self) -> u64 {
        match self {
            Self::Single { length, .. } => *length,
            Self::Multiple { files } => files.iter().map(|file| file.length).sum(),
        }
    }
}

impl File {
    impl_getters!(
        length._copy() => u64,
        path.as_slice() => &[String],
        md5sum.clone() => Option<Md5Hash>,
        extra._ref() => &Value,
    );
}

#[cfg(test)]
mod tests {
    use std::fmt;

    use serde::de::DeserializeOwned;

    use bt_bencode::bencode;

    use super::*;

    const MD5_HASH_TESTDATA: &str = "00112233445566778899aabbccddeeff";

    fn metainfo_testdata() -> [(Metainfo, Value); 2] {
        let [(_, info_dict), ..] = info_testdata();

        let info = bt_bencode::to_bytes(&info_dict).unwrap();
        let info = bt_bencode::from_buf::<_, WithRaw<Info>>(info).unwrap();

        [
            (
                Metainfo {
                    announce: None,
                    info: info.clone(),
                    info_hash: OnceLock::new(),
                    announce_list: None,
                    nodes: None,
                    url_list: None,
                    comment: None,
                    created_by: None,
                    creation_date: None,
                    encoding: None,
                    extra: bencode!({}),
                },
                bencode!({b"info": info_dict.clone()}),
            ),
            (
                Metainfo {
                    announce: Some("foo".to_string()),
                    info,
                    info_hash: OnceLock::new(),
                    announce_list: Some(vec![vec!["bar".to_string()]]),
                    nodes: Some(vec![("spam".to_string(), 101)]),
                    url_list: Some(vec!["egg".to_string()]),
                    comment: Some("hello".to_string()),
                    created_by: Some("world".to_string()),
                    creation_date: Some(Timestamp::from_timestamp_secs(42).unwrap()),
                    encoding: Some("xyz".to_string()),
                    extra: bencode!({b"": b""}),
                },
                bencode!({
                    b"announce": b"foo",
                    b"info": info_dict,
                    b"announce-list": [[b"bar"]],
                    b"nodes": [[b"spam", 101]],
                    b"url-list": [b"egg"],
                    b"comment": b"hello",
                    b"created by": b"world",
                    b"creation date": 42,
                    b"encoding": b"xyz",
                    b"": b"",
                }),
            ),
        ]
    }

    fn info_testdata() -> [(Info, Value); 4] {
        let mut files = Vec::new();
        let mut file_list = Vec::new();
        for (f, v) in file_testdata() {
            files.push(f);
            file_list.push(v);
        }
        let file_list = Value::List(file_list);

        [
            (
                Info {
                    name: "".to_string(),
                    piece_length: 0,
                    pieces: PieceHashes::new((*b"").into()).unwrap(),
                    mode: Mode::Single {
                        length: 0,
                        md5sum: None,
                    },
                    private: None,
                    extra: bencode!({}),
                },
                bencode!({
                    b"name": b"",
                    b"piece length": 0,
                    b"pieces": b"",
                    b"length": 0,
                }),
            ),
            (
                Info {
                    name: "foo".to_string(),
                    piece_length: 256,
                    pieces: PieceHashes::new([0u8; 20].into()).unwrap(),
                    mode: Mode::Single {
                        length: 42,
                        md5sum: Some(MD5_HASH_TESTDATA.parse().unwrap()),
                    },
                    private: Some(false),
                    extra: bencode!({b"x": 2, b"spam": b"egg"}),
                },
                bencode!({
                    b"name": b"foo",
                    b"piece length": 256,
                    b"pieces": &[0u8; 20],
                    b"length": 42,
                    b"md5sum": MD5_HASH_TESTDATA.as_bytes(),
                    b"private": 0,
                    b"x": 2,
                    b"spam": b"egg",
                }),
            ),
            (
                Info {
                    name: "hello".to_string(),
                    piece_length: 13,
                    pieces: PieceHashes::new([0u8; 40].into()).unwrap(),
                    mode: Mode::Multiple { files: vec![] },
                    private: Some(true),
                    extra: bencode!({b"": b""}),
                },
                bencode!({
                    b"name": b"hello",
                    b"piece length": 13,
                    b"pieces": &[0u8; 40],
                    b"files": [],
                    b"private": 1,
                    b"": b"",
                }),
            ),
            (
                Info {
                    name: "world".to_string(),
                    piece_length: 17,
                    pieces: PieceHashes::new([0u8; 60].into()).unwrap(),
                    mode: Mode::Multiple { files },
                    private: Some(true),
                    extra: bencode!({b"\x80": b"\x80"}),
                },
                bencode!({
                    b"name": b"world",
                    b"piece length": 17,
                    b"pieces": &[0u8; 60],
                    b"files": file_list,
                    b"private": 1,
                    b"\x80": b"\x80",
                }),
            ),
        ]
    }

    fn file_testdata() -> [(File, Value); 2] {
        [
            (
                File {
                    length: 0,
                    path: vec![],
                    md5sum: None,
                    extra: bencode!({}),
                },
                bencode!({b"length": 0, b"path": []}),
            ),
            (
                File {
                    length: 42,
                    path: vec!["foo".to_string()],
                    md5sum: Some(MD5_HASH_TESTDATA.parse().unwrap()),
                    extra: bencode!({b"x": 2, b"spam": b"egg"}),
                },
                bencode!({
                    b"length": 42,
                    b"path": [b"foo"],
                    b"md5sum": MD5_HASH_TESTDATA.as_bytes(),
                    b"x": 2,
                    b"spam": b"egg",
                }),
            ),
        ]
    }

    fn test<T>(object: T, value: Value)
    where
        T: DeserializeOwned + Serialize,
        T: Clone + fmt::Debug + PartialEq,
    {
        assert_eq!(bt_bencode::from_value(value.clone()), Ok(object.clone()));
        assert_eq!(bt_bencode::to_value(&object), Ok(value));
    }

    #[test]
    fn metainfo() {
        for (metainfo, value) in metainfo_testdata() {
            // Deserializing `WithRaw<Info>` from `value` is not supported for now.
            let bencode = bt_bencode::to_bytes(&value).unwrap();
            assert_eq!(bt_bencode::from_buf(bencode), Ok(metainfo.clone()));
            assert_eq!(bt_bencode::to_value(&metainfo), Ok(value.clone()));

            let info_dict = value
                .as_dictionary()
                .unwrap()
                .get(b"info".as_slice())
                .unwrap();
            assert_eq!(
                metainfo.info_blob(),
                bt_bencode::to_bytes(info_dict).unwrap(),
            );
        }
    }

    #[test]
    fn info() {
        for (info, value) in info_testdata() {
            test(info, value);
        }
    }

    #[test]
    fn file() {
        for (file, value) in file_testdata() {
            test(file, value);
        }
    }
}
