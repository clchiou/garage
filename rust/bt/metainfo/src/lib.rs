#![feature(debug_closure_helpers)]

mod optional;
mod sanity;

use std::sync::OnceLock;

use serde::{Deserialize, Serialize};

use bt_base::{InfoHash, Md5Hash, PieceHashes};
use bt_bencode::{Value, WithRaw};

//
// Implementer's Notes: Almost all fields are optional.  `bt_bencode` does not have the concept of
// an "optional field" and treats an `Option<T>` field as a list field.  Here, we introduce this
// concept and treat it as a present/absent `T` field.
//
// TODO: We use `serde(default, skip_serializing_if = "Option::is_none", with = "optional")` to
// implement optional fields.  This approach is repetitive and cumbersome.  Could we introduce a
// container attribute, similar to `serde_with::skip_serializing_none`?
//

pub use g1_chrono::{Timestamp, TimestampExt};

pub use self::sanity::{Insane, Symptom};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Metainfo {
    #[serde(default, skip_serializing_if = "Option::is_none", with = "optional")]
    announce: Option<String>,

    info: WithRaw<Info>,
    #[serde(skip)]
    info_hash: OnceLock<InfoHash>,

    // BEP 12 Multitracker Metadata Extension
    #[serde(rename = "announce-list")]
    #[serde(default, skip_serializing_if = "Option::is_none", with = "optional")]
    announce_list: Option<Vec<Vec<String>>>,

    // BEP 5 DHT Protocol
    #[serde(default, skip_serializing_if = "Option::is_none", with = "optional")]
    nodes: Option<Vec<(String, u16)>>,

    // BEP 19 WebSeed - HTTP/FTP Seeding (GetRight style)
    #[serde(rename = "url-list")]
    #[serde(default, skip_serializing_if = "Option::is_none", with = "optional")]
    url_list: Option<Vec<String>>,

    //
    // Non-BEP fields.
    //
    #[serde(default, skip_serializing_if = "Option::is_none", with = "optional")]
    comment: Option<String>,

    #[serde(rename = "created by")]
    #[serde(default, skip_serializing_if = "Option::is_none", with = "optional")]
    created_by: Option<String>,

    #[serde(rename = "creation date")]
    #[serde(
        default,
        skip_serializing_if = "Option::is_none",
        with = "optional::timestamp"
    )]
    creation_date: Option<Timestamp>,

    #[serde(default, skip_serializing_if = "Option::is_none", with = "optional")]
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

#[derive(Deserialize, Serialize)]
struct FlatInfo {
    name: String,
    #[serde(rename = "piece length")]
    piece_length: u64,
    pieces: PieceHashes,

    // Mode::Single
    #[serde(default, skip_serializing_if = "Option::is_none", with = "optional")]
    length: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none", with = "optional")]
    md5sum: Option<Md5Hash>,

    // Mode::Multiple
    #[serde(default, skip_serializing_if = "Option::is_none", with = "optional")]
    files: Option<Vec<File>>,

    #[serde(default, skip_serializing_if = "Option::is_none", with = "optional")]
    private: Option<bool>,

    #[serde(flatten)]
    extra: Value,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct File {
    length: u64,
    path: Vec<String>,

    //
    // Non-BEP fields.
    //
    #[serde(default, skip_serializing_if = "Option::is_none", with = "optional")]
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

    use bt_bencode::own::bytes::{ByteString, Integer};

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
                    extra: vd([]),
                },
                vd([(b"info", info_dict.clone())]),
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
                    extra: vd([(b"", vb(b""))]),
                },
                vd([
                    (b"announce", vb(b"foo")),
                    (b"info", info_dict),
                    (b"announce-list", vl([vl([vb(b"bar")])])),
                    (b"nodes", vl([vl([vb(b"spam"), vi(101)])])),
                    (b"url-list", vl([vb(b"egg")])),
                    (b"comment", vb(b"hello")),
                    (b"created by", vb(b"world")),
                    (b"creation date", vi(42)),
                    (b"encoding", vb(b"xyz")),
                    (b"", vb(b"")),
                ]),
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
                    extra: vd([]),
                },
                vd([
                    (b"name", vb(b"")),
                    (b"piece length", vi(0)),
                    (b"pieces", vb(b"")),
                    (b"length", vi(0)),
                ]),
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
                    extra: vd([(b"x", vi(2)), (b"spam", vb(b"egg"))]),
                },
                vd([
                    (b"name", vb(b"foo")),
                    (b"piece length", vi(256)),
                    (b"pieces", vb(&[0u8; 20])),
                    (b"length", vi(42)),
                    (b"md5sum", vb(MD5_HASH_TESTDATA.as_bytes())),
                    (b"private", vi(0)),
                    (b"x", vi(2)),
                    (b"spam", vb(b"egg")),
                ]),
            ),
            (
                Info {
                    name: "hello".to_string(),
                    piece_length: 13,
                    pieces: PieceHashes::new([0u8; 40].into()).unwrap(),
                    mode: Mode::Multiple { files: vec![] },
                    private: Some(true),
                    extra: vd([(b"", vb(b""))]),
                },
                vd([
                    (b"name", vb(b"hello")),
                    (b"piece length", vi(13)),
                    (b"pieces", vb(&[0u8; 40])),
                    (b"files", vl([])),
                    (b"private", vi(1)),
                    (b"", vb(b"")),
                ]),
            ),
            (
                Info {
                    name: "world".to_string(),
                    piece_length: 17,
                    pieces: PieceHashes::new([0u8; 60].into()).unwrap(),
                    mode: Mode::Multiple { files },
                    private: Some(true),
                    extra: vd([(b"\x80", vb(b"\x80"))]),
                },
                vd([
                    (b"name", vb(b"world")),
                    (b"piece length", vi(17)),
                    (b"pieces", vb(&[0u8; 60])),
                    (b"files", file_list),
                    (b"private", vi(1)),
                    (b"\x80", vb(b"\x80")),
                ]),
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
                    extra: vd([]),
                },
                vd([(b"length", vi(0)), (b"path", vl([]))]),
            ),
            (
                File {
                    length: 42,
                    path: vec!["foo".to_string()],
                    md5sum: Some(MD5_HASH_TESTDATA.parse().unwrap()),
                    extra: vd([(b"x", vi(2)), (b"spam", vb(b"egg"))]),
                },
                vd([
                    (b"length", vi(42)),
                    (b"path", vl([vb(b"foo")])),
                    (b"md5sum", vb(MD5_HASH_TESTDATA.as_bytes())),
                    (b"x", vi(2)),
                    (b"spam", vb(b"egg")),
                ]),
            ),
        ]
    }

    fn vb(bytes: &[u8]) -> Value {
        Value::ByteString(ByteString::copy_from_slice(bytes))
    }

    fn vi(integer: Integer) -> Value {
        Value::Integer(integer)
    }

    fn vl<const N: usize>(items: [Value; N]) -> Value {
        Value::List(items.into())
    }

    fn vd<const N: usize>(items: [(&[u8], Value); N]) -> Value {
        Value::Dictionary(
            items
                .into_iter()
                .map(|(k, v)| (ByteString::copy_from_slice(k), v))
                .collect(),
        )
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
