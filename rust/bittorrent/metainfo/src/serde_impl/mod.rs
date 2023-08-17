mod convert;

use std::collections::BTreeMap;

use serde_bytes::Bytes;

use bittorrent_bencode::{
    borrow,
    convert::{from_dict, from_str, from_vec, to_dict, to_int, to_str, to_vec},
    dict::{DictionaryInsert, DictionaryRemove},
    own,
};

use crate::{Error, File, Info, Metainfo, Mode};

use self::convert::*;

// `Metainfo` dictionary keys.
const ANNOUNCE: &[u8] = b"announce";
const ANNOUNCE_LIST: &[u8] = b"announce-list";
const NODES: &[u8] = b"nodes";
const URL_LIST: &[u8] = b"url-list";
const COMMENT: &[u8] = b"comment";
const CREATED_BY: &[u8] = b"created by";
const CREATION_DATE: &[u8] = b"creation date";
const ENCODING: &[u8] = b"encoding";
const INFO: &[u8] = b"info";

// `Info` dictionary keys.
const NAME: &[u8] = b"name";
const PIECE_LENGTH: &[u8] = b"piece length";
const PIECES: &[u8] = b"pieces";
const PRIVATE: &[u8] = b"private";

// `Mode` and `File` dictionary keys.
const LENGTH: &[u8] = b"length";
const MD5SUM: &[u8] = b"md5sum";
const FILES: &[u8] = b"files";
const PATH: &[u8] = b"path";

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for Metainfo<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        let this = Self {
            announce: dict.remove_str::<Error>(ANNOUNCE)?,
            announce_list: dict
                .remove(ANNOUNCE_LIST)
                .map(to_announce_list)
                .transpose()?,
            nodes: dict.remove(NODES).map(to_nodes).transpose()?,
            url_list: dict.remove(URL_LIST).map(to_url_list).transpose()?,

            comment: dict.remove_str::<Error>(COMMENT)?,
            created_by: dict.remove_str::<Error>(CREATED_BY)?,
            creation_date: dict
                .remove_int::<Error>(CREATION_DATE)?
                .map(to_timestamp)
                .transpose()?,
            encoding: dict.remove_str::<Error>(ENCODING)?,
            info: Info::try_from(dict.must_remove::<Error>(INFO)?)?,

            extra: dict,
        };
        this.sanity_check()?;
        Ok(this)
    }
}

impl<'a> From<Metainfo<'a>> for BTreeMap<&'a Bytes, own::Value> {
    fn from(metainfo: Metainfo<'a>) -> Self {
        let mut dict = from_dict(metainfo.extra, Bytes::new);

        dict.insert_from(ANNOUNCE, metainfo.announce, from_str);
        dict.insert_from(ANNOUNCE_LIST, metainfo.announce_list, from_announce_list);
        dict.insert_from(NODES, metainfo.nodes, from_nodes);
        dict.insert_from(URL_LIST, metainfo.url_list, from_url_list);

        dict.insert_from(COMMENT, metainfo.comment, from_str);
        dict.insert_from(CREATED_BY, metainfo.created_by, from_str);
        dict.insert_from(CREATION_DATE, metainfo.creation_date, from_timestamp);
        dict.insert_from(ENCODING, metainfo.encoding, from_str);
        dict.insert(Bytes::new(INFO), metainfo.info.into());

        dict
    }
}

impl<'a> TryFrom<borrow::Value<'a>> for Info<'a> {
    type Error = Error;

    fn try_from(value: borrow::Value<'a>) -> Result<Self, Self::Error> {
        let (mut dict, raw_info) = to_dict::<Error>(value)?;
        let this = Self {
            raw_info: raw_info.unwrap(),
            name: dict.must_remove::<Error>(NAME).and_then(to_str)?,
            mode: Mode::decode(&mut dict)?,
            piece_length: dict
                .must_remove::<Error>(PIECE_LENGTH)
                .and_then(to_int)
                .and_then(to_length)?,
            pieces: dict.must_remove::<Error>(PIECES).and_then(to_pieces)?,
            private: dict.remove_int::<Error>(PRIVATE)?.map(to_private),
            extra: dict,
        };
        this.sanity_check()?;
        Ok(this)
    }
}

impl<'a> From<Info<'a>> for own::Value {
    fn from(info: Info<'a>) -> Self {
        let mut dict = from_dict(info.extra, own::ByteString::from);
        dict.insert(NAME.into(), from_str(info.name));
        info.mode.encode_into(&mut dict);
        dict.insert(PIECE_LENGTH.into(), from_length(info.piece_length));
        dict.insert(PIECES.into(), from_pieces(info.pieces));
        dict.insert_from(PRIVATE, info.private, from_private);
        dict.into()
    }
}

impl<'a> Mode<'a> {
    fn decode(dict: &mut BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Error> {
        // TODO: "length" and "files" should not both be present, but for now we are not checking
        // this.
        Ok(match dict.remove_int::<Error>(LENGTH)? {
            Some(length) => Self::SingleFile {
                length: to_length(length)?,
                md5sum: dict.remove_str::<Error>(MD5SUM)?,
            },
            None => Self::MultiFile {
                files: dict
                    .must_remove::<Error>(FILES)
                    .and_then(|value| to_vec(value, File::try_from))?,
            },
        })
    }

    fn encode_into(self, dict: &mut BTreeMap<own::ByteString, own::Value>) {
        match self {
            Self::SingleFile { length, md5sum } => {
                dict.insert(LENGTH.into(), from_length(length));
                dict.insert_from(MD5SUM, md5sum, from_str);
            }
            Self::MultiFile { files } => {
                dict.insert(
                    FILES.into(),
                    files
                        .into_iter()
                        .map(File::into)
                        .collect::<Vec<own::Value>>()
                        .into(),
                );
            }
        }
    }
}

impl<'a> TryFrom<borrow::Value<'a>> for File<'a> {
    type Error = Error;

    fn try_from(value: borrow::Value<'a>) -> Result<Self, Self::Error> {
        let (mut dict, _) = to_dict::<Error>(value)?;
        Ok(Self {
            path: dict
                .must_remove::<Error>(PATH)
                .and_then(|value| to_vec(value, to_str))?,
            length: dict
                .must_remove::<Error>(LENGTH)
                .and_then(to_int)
                .and_then(to_length)?,
            md5sum: dict.remove_str::<Error>(MD5SUM)?,
            extra: dict,
        })
    }
}

impl<'a> From<File<'a>> for own::Value {
    fn from(file: File<'a>) -> Self {
        let mut dict = from_dict(file.extra, own::ByteString::from);
        dict.insert(PATH.into(), from_vec(file.path, from_str));
        dict.insert(LENGTH.into(), from_length(file.length));
        dict.insert_from(MD5SUM, file.md5sum, from_str);
        dict.into()
    }
}

#[cfg(test)]
mod tests {
    use chrono::{TimeZone, Utc};

    use bittorrent_bencode::serde as serde_bencode;

    use super::*;

    fn new_bytes(bytes: &[u8]) -> borrow::Value<'_> {
        borrow::Value::new_byte_string(bytes)
    }

    #[test]
    fn metainfo() {
        fn test(dict: BTreeMap<&[u8], borrow::Value>, expect: Metainfo) {
            let owned_dict: BTreeMap<&Bytes, own::Value> = dict
                .iter()
                .map(|(key, value)| (Bytes::new(key), value.to_owned()))
                .collect();

            let mut metainfo_buffer = Vec::new();
            borrow::Value::from(dict.clone()).encode(&mut metainfo_buffer);
            let mut info_buffer = Vec::new();
            borrow::Value::from(dict.get(b"info".as_slice()).unwrap().clone())
                .encode(&mut info_buffer);

            assert_eq!(Metainfo::try_from(dict.clone()), Ok(expect.clone()));
            assert_eq!(
                <BTreeMap<&Bytes, own::Value>>::from(expect.clone()),
                owned_dict.clone(),
            );

            let metainfo: Metainfo = serde_bencode::from_bytes(&metainfo_buffer).unwrap();
            assert_eq!(metainfo, expect);
            assert_eq!(metainfo.info.raw_info, &info_buffer);

            assert_eq!(&serde_bencode::to_bytes(&expect).unwrap(), &metainfo_buffer);
        }

        let dict = BTreeMap::from([
            (b"announce".as_slice(), new_bytes(b"foo")),
            (
                b"announce-list".as_slice(),
                vec![vec![new_bytes(b"bar")].into()].into(),
            ),
            (
                b"nodes".as_slice(),
                vec![vec![new_bytes(b"host"), 8000.into()].into()].into(),
            ),
            (
                b"url-list".as_slice(),
                vec![new_bytes(b"url0"), new_bytes(b"url1")].into(),
            ),
            (b"comment".as_slice(), new_bytes(b"spam")),
            (b"created by".as_slice(), new_bytes(b"egg")),
            (b"creation date".as_slice(), 42.into()),
            (b"encoding".as_slice(), new_bytes(b"utf-8")),
            (
                b"info".as_slice(),
                BTreeMap::from([
                    (b"name".as_slice(), new_bytes(b"foo")),
                    (b"length".as_slice(), 100.into()),
                    (b"md5sum".as_slice(), new_bytes(b"deadbeef")),
                    (b"piece length".as_slice(), 512.into()),
                    (b"pieces".as_slice(), new_bytes(b"01234567890123456789")),
                    (b"private".as_slice(), 1.into()),
                    (b"info extra stuff".as_slice(), 2.into()),
                ])
                .into(),
            ),
            (b"extra stuff".as_slice(), 3.into()),
        ]);
        let expect = Metainfo {
            announce: Some("foo"),
            announce_list: Some(vec![vec!["bar"]]),
            nodes: Some(vec![("host", 8000)]),
            url_list: Some(vec!["url0", "url1"]),
            comment: Some("spam"),
            created_by: Some("egg"),
            creation_date: Some(Utc.timestamp_opt(42, 0).single().unwrap()),
            encoding: Some("utf-8"),
            info: Info {
                raw_info: b"".as_slice(),
                name: "foo",
                mode: Mode::SingleFile {
                    length: 100,
                    md5sum: Some("deadbeef"),
                },
                piece_length: 512,
                pieces: vec![b"01234567890123456789".as_slice()],
                private: Some(true),
                extra: BTreeMap::from([(b"info extra stuff".as_slice(), 2.into())]),
            },
            extra: BTreeMap::from([(b"extra stuff".as_slice(), 3.into())]),
        };
        test(dict, expect);

        let dict = BTreeMap::from([(
            b"info".as_slice(),
            BTreeMap::from([
                (b"name".as_slice(), new_bytes(b"foo")),
                (
                    b"files",
                    vec![BTreeMap::from([
                        (
                            b"path".as_slice(),
                            vec![new_bytes(b"spam"), new_bytes(b"egg")].into(),
                        ),
                        (b"length".as_slice(), 100.into()),
                        (b"md5sum".as_slice(), new_bytes(b"deadbeef")),
                        (b"extra stuff".as_slice(), 42.into()),
                    ])
                    .into()]
                    .into(),
                ),
                (b"piece length".as_slice(), 512.into()),
                (b"pieces".as_slice(), new_bytes(b"01234567890123456789")),
            ])
            .into(),
        )]);
        let expect = Metainfo {
            announce: None,
            announce_list: None,
            nodes: None,
            url_list: None,
            comment: None,
            created_by: None,
            creation_date: None,
            encoding: None,
            info: Info {
                raw_info: b"".as_slice(),
                name: "foo",
                mode: Mode::MultiFile {
                    files: vec![File {
                        path: vec!["spam", "egg"],
                        length: 100,
                        md5sum: Some("deadbeef"),
                        extra: BTreeMap::from([(b"extra stuff".as_slice(), 42.into())]),
                    }],
                },
                piece_length: 512,
                pieces: vec![b"01234567890123456789".as_slice()],
                private: None,
                extra: BTreeMap::new(),
            },
            extra: BTreeMap::new(),
        };
        test(dict, expect);
    }
}
