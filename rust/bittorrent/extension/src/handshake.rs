use std::collections::BTreeMap;

use bytes::BufMut;
use serde::{Deserialize, Serialize};
use serde_bytes::Bytes;

use g1_base::fmt::DebugExt;

use bittorrent_bencode::{
    borrow,
    convert::{from_dict, to_dict, to_int, to_str},
    dict::{DictionaryInsert, DictionaryRemove},
    own, serde as serde_bencode, FormatDictionary,
};

use crate::{metadata, Error, EXTENSIONS};

#[derive(Clone, DebugExt, Deserialize, Eq, PartialEq, Serialize)]
#[serde(
    try_from = "BTreeMap<&[u8], borrow::Value>",
    into = "BTreeMap<&Bytes, own::Value>"
)]
pub struct Handshake<'a> {
    // BEP 10 does not seem to require that extension names be valid UTF-8 strings, but I think it
    // should be safe to assume they are.
    //
    // We need this `serde(borrow)` to prompt `Deserialize` to include a `'de: 'a` bound.
    #[serde(borrow)]
    pub extension_ids: BTreeMap<&'a str, u8>,

    pub metadata_size: Option<usize>, // BEP 9

    #[debug(with = FormatDictionary)]
    pub extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

impl<'a> Handshake<'a> {
    // TODO: How can we make this id value match the global `EXTENSIONS` array index?
    pub const ID: u8 = 0;

    pub fn new(metadata_size: Option<usize>) -> Self {
        Self {
            extension_ids: EXTENSIONS
                .iter()
                .enumerate()
                .filter_map(|(id, extension)| {
                    let id = u8::try_from(id).unwrap();
                    (id != 0 && (extension.is_enabled)()).then_some((extension.name, id))
                })
                .collect(),
            metadata_size,
            extra: BTreeMap::new(),
        }
    }

    pub fn encode(&self, buffer: &mut impl BufMut) {
        self.serialize(serde_bencode::Serializer)
            .unwrap()
            .encode(buffer);
    }
}

const EXTENSION_IDS: &[u8] = b"m";
const METADATA_SIZE: &[u8] = b"metadata_size"; // BEP 9

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for Handshake<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        Ok(Self {
            extension_ids: dict
                .remove(EXTENSION_IDS)
                .map(to_extension_ids)
                .unwrap_or_else(|| Ok(BTreeMap::new()))?,
            metadata_size: dict
                .remove_int::<Error>(METADATA_SIZE)?
                .map(metadata::to_metadata_size)
                .transpose()?,
            extra: dict,
        })
    }
}

impl<'a> From<Handshake<'a>> for BTreeMap<&'a Bytes, own::Value> {
    fn from(handshake: Handshake<'a>) -> Self {
        let mut dict = from_dict(handshake.extra, Bytes::new);
        if !handshake.extension_ids.is_empty() {
            dict.insert(
                Bytes::new(EXTENSION_IDS),
                from_extension_ids(handshake.extension_ids),
            );
        }
        dict.insert_from(
            METADATA_SIZE,
            handshake.metadata_size,
            metadata::from_metadata_size,
        );
        dict
    }
}

fn to_extension_ids(value: borrow::Value) -> Result<BTreeMap<&str, u8>, Error> {
    let (dict, _) = to_dict::<Error>(value)?;
    dict.into_iter()
        .map(|(name, id)| {
            Ok((
                to_str::<Error>(borrow::Value::ByteString(name))?,
                to_extension_id(id)?,
            ))
        })
        .try_collect()
}

fn from_extension_ids(extension_ids: BTreeMap<&str, u8>) -> own::Value {
    extension_ids
        .into_iter()
        .map(|(name, id)| (name.as_bytes().into(), from_extension_id(id)))
        .collect::<BTreeMap<own::ByteString, own::Value>>()
        .into()
}

fn to_extension_id(value: borrow::Value) -> Result<u8, Error> {
    let id = to_int::<Error>(value)?;
    id.try_into().map_err(|_| Error::InvalidExtensionId { id })
}

fn from_extension_id(id: u8) -> own::Value {
    i64::from(id).into()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn id() {
        assert_eq!(EXTENSIONS[usize::from(Handshake::ID)].name, "");
    }

    #[test]
    fn new() {
        assert_eq!(
            Handshake::new(Some(42)),
            Handshake {
                extension_ids: BTreeMap::from([("ut_metadata", 1)]),
                metadata_size: Some(42),
                extra: BTreeMap::new(),
            },
        );
    }

    #[test]
    fn conversion() {
        fn test<'a>(decode: BTreeMap<&'a [u8], borrow::Value<'a>>, handshake: Handshake<'a>) {
            let encode: BTreeMap<&'a Bytes, own::Value> = decode
                .iter()
                .map(|(key, value)| (Bytes::new(key), value.to_owned()))
                .collect();
            assert_eq!(Handshake::try_from(decode), Ok(handshake.clone()));
            assert_eq!(BTreeMap::from(handshake), encode);
        }

        test(
            BTreeMap::new(),
            Handshake {
                extension_ids: BTreeMap::from([]),
                metadata_size: None,
                extra: BTreeMap::from([]),
            },
        );
        test(
            BTreeMap::from([
                (
                    b"m".as_slice(),
                    BTreeMap::from([(b"foo".as_slice(), 0.into())]).into(),
                ),
                (b"metadata_size".as_slice(), 1.into()),
                (b"bar".as_slice(), 2.into()),
            ]),
            Handshake {
                extension_ids: BTreeMap::from([("foo", 0)]),
                metadata_size: Some(1),
                extra: BTreeMap::from([(b"bar".as_slice(), 2.into())]),
            },
        );
    }

    #[test]
    fn extension_ids() {
        assert_eq!(
            to_extension_ids(BTreeMap::from([]).into()),
            Ok(BTreeMap::from([])),
        );
        assert_eq!(
            to_extension_ids(BTreeMap::from([(b"foo".as_slice(), 42.into())]).into()),
            Ok(BTreeMap::from([("foo", 42)])),
        );

        assert_eq!(
            from_extension_ids(BTreeMap::from([])),
            BTreeMap::from([]).into(),
        );
        assert_eq!(
            from_extension_ids(BTreeMap::from([("foo", 42)])),
            BTreeMap::from([(b"foo".as_slice().into(), 42.into())]).into(),
        );
    }

    #[test]
    fn extension_id() {
        assert_eq!(to_extension_id(0.into()), Ok(0));
        assert_eq!(to_extension_id(42.into()), Ok(42));
        assert_eq!(
            to_extension_id((-1).into()),
            Err(Error::InvalidExtensionId { id: -1 }),
        );
        assert_eq!(
            to_extension_id(256.into()),
            Err(Error::InvalidExtensionId { id: 256 }),
        );

        assert_eq!(from_extension_id(0), 0.into());
        assert_eq!(from_extension_id(42), 42.into());
    }
}
