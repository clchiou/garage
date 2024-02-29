use std::cmp;
use std::collections::BTreeMap;
use std::ops::Range;

use bytes::BufMut;
use serde::{de::Error as _, Serialize};
use serde_bytes::Bytes;

use g1_base::fmt::DebugExt;

use bittorrent_bencode::{
    borrow,
    convert::{from_dict, to_dict, to_int},
    dict::{DictionaryInsert, DictionaryRemove},
    own, serde as serde_bencode, FormatDictionary,
};

use crate::Error;

g1_param::define!(pub(crate) enable: bool = true); // BEP 9

// We do not use `serde` to deserialize the metadata because the bencode-then-payload format does
// not conform well to the way the `serde` API works.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(into = "BTreeMap<&Bytes, own::Value>")]
pub enum Metadata<'a> {
    Request(Request<'a>),
    Data(Data<'a>),
    Reject(Reject<'a>),
}

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub struct Request<'a> {
    pub piece: usize,

    #[debug(with = FormatDictionary)]
    pub extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub struct Data<'a> {
    pub piece: usize,
    pub total_size: Option<usize>,
    pub payload: &'a [u8],

    #[debug(with = FormatDictionary)]
    pub extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

#[derive(Clone, DebugExt, Eq, PartialEq)]
pub struct Reject<'a> {
    pub piece: usize,

    #[debug(with = FormatDictionary)]
    pub extra: BTreeMap<&'a [u8], borrow::Value<'a>>,
}

impl<'a> Metadata<'a> {
    // TODO: How can we make this id value match the global `EXTENSIONS` array index?
    pub const ID: u8 = 1;
    // BEP 9 defines a fixed block size.
    pub const BLOCK_SIZE: usize = 16384;

    pub fn num_pieces(metadata_size: usize) -> usize {
        metadata_size.div_ceil(Self::BLOCK_SIZE)
    }

    pub fn byte_range(piece: usize, metadata_size: usize) -> Range<usize> {
        let start = piece * Self::BLOCK_SIZE;
        assert!(start < metadata_size);
        start..cmp::min(start + Self::BLOCK_SIZE, metadata_size)
    }

    pub fn decode(mut buffer: &'a [u8]) -> Result<Self, serde_bencode::Error> {
        let header = borrow::Value::decode(&mut buffer)
            .map_err(|source| serde_bencode::Error::Decode { source })?;
        Self::try_from((header, buffer)).map_err(serde_bencode::Error::custom)
    }

    pub fn decode_lenient(mut buffer: &'a [u8]) -> Result<Self, serde_bencode::Error> {
        let header = borrow::Value::<false>::decode(&mut buffer)
            .map_err(|source| serde_bencode::Error::Decode { source })?;
        Self::try_from((header.to_strict(), buffer)).map_err(serde_bencode::Error::custom)
    }

    pub fn encode(&self, buffer: &mut impl BufMut) {
        self.serialize(serde_bencode::Serializer)
            .unwrap()
            .encode(buffer);
        if let Self::Data(data) = self {
            buffer.put_slice(data.payload);
        }
    }
}

impl<'a> Request<'a> {
    pub fn new(piece: usize) -> Self {
        Self {
            piece,
            extra: BTreeMap::new(),
        }
    }
}

impl<'a> Data<'a> {
    pub fn new(piece: usize, total_size: Option<usize>, payload: &'a [u8]) -> Self {
        assert!(payload.len() <= Metadata::BLOCK_SIZE);
        Self {
            piece,
            total_size,
            payload,
            extra: BTreeMap::new(),
        }
    }
}

impl<'a> Reject<'a> {
    pub fn new(piece: usize) -> Self {
        Self {
            piece,
            extra: BTreeMap::new(),
        }
    }
}

const MESSAGE_TYPE: &[u8] = b"msg_type";
const PIECE: &[u8] = b"piece";
const TOTAL_SIZE: &[u8] = b"total_size";

const REQUEST: i64 = 0;
const DATA: i64 = 1;
const REJECT: i64 = 2;

impl<'a> TryFrom<(borrow::Value<'a>, &'a [u8])> for Metadata<'a> {
    type Error = Error;

    fn try_from((header, payload): (borrow::Value<'a>, &'a [u8])) -> Result<Self, Self::Error> {
        let (mut dict, _) = to_dict::<Error>(header)?;
        match dict.must_remove::<Error>(MESSAGE_TYPE).and_then(to_int)? {
            REQUEST => Ok(Metadata::Request(Request::try_from(dict)?)),
            DATA => Ok(Metadata::Data(Data::try_from((dict, payload))?)),
            REJECT => Ok(Metadata::Reject(Reject::try_from(dict)?)),
            message_type => Err(Error::UnknownMetadataMessageType { message_type }),
        }
    }
}

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for Request<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        Ok(Self {
            piece: dict
                .must_remove(PIECE)
                .and_then(to_int)
                .and_then(to_piece)?,
            extra: dict,
        })
    }
}

impl<'a> TryFrom<(BTreeMap<&'a [u8], borrow::Value<'a>>, &'a [u8])> for Data<'a> {
    type Error = Error;

    fn try_from(
        (mut dict, payload): (BTreeMap<&'a [u8], borrow::Value<'a>>, &'a [u8]),
    ) -> Result<Self, Self::Error> {
        Ok(Self {
            piece: dict
                .must_remove(PIECE)
                .and_then(to_int)
                .and_then(to_piece)?,
            total_size: dict
                .remove_int::<Error>(TOTAL_SIZE)?
                .map(to_metadata_size)
                .transpose()?,
            payload,
            extra: dict,
        })
    }
}

impl<'a> TryFrom<BTreeMap<&'a [u8], borrow::Value<'a>>> for Reject<'a> {
    type Error = Error;

    fn try_from(mut dict: BTreeMap<&'a [u8], borrow::Value<'a>>) -> Result<Self, Self::Error> {
        Ok(Self {
            piece: dict
                .must_remove(PIECE)
                .and_then(to_int)
                .and_then(to_piece)?,
            extra: dict,
        })
    }
}

impl<'a> From<Metadata<'a>> for BTreeMap<&'a Bytes, own::Value> {
    fn from(metadata: Metadata<'a>) -> Self {
        match metadata {
            Metadata::Request(request) => request.into(),
            Metadata::Data(data) => data.into(),
            Metadata::Reject(reject) => reject.into(),
        }
    }
}

impl<'a> From<Request<'a>> for BTreeMap<&'a Bytes, own::Value> {
    fn from(request: Request<'a>) -> Self {
        let mut dict = from_dict(request.extra, Bytes::new);
        dict.insert(Bytes::new(MESSAGE_TYPE), REQUEST.into());
        dict.insert(Bytes::new(PIECE), from_piece(request.piece));
        dict
    }
}

impl<'a> From<Data<'a>> for BTreeMap<&'a Bytes, own::Value> {
    fn from(data: Data<'a>) -> Self {
        let mut dict = from_dict(data.extra, Bytes::new);
        dict.insert(Bytes::new(MESSAGE_TYPE), DATA.into());
        dict.insert(Bytes::new(PIECE), from_piece(data.piece));
        dict.insert_from(TOTAL_SIZE, data.total_size, from_metadata_size);
        dict
    }
}

impl<'a> From<Reject<'a>> for BTreeMap<&'a Bytes, own::Value> {
    fn from(reject: Reject<'a>) -> Self {
        let mut dict = from_dict(reject.extra, Bytes::new);
        dict.insert(Bytes::new(MESSAGE_TYPE), REJECT.into());
        dict.insert(Bytes::new(PIECE), from_piece(reject.piece));
        dict
    }
}

fn to_piece(piece: i64) -> Result<usize, Error> {
    piece
        .try_into()
        .map_err(|_| Error::InvalidMetadataPiece { piece })
}

fn from_piece(piece: usize) -> own::Value {
    i64::try_from(piece).unwrap().into()
}

pub(crate) fn to_metadata_size(size: i64) -> Result<usize, Error> {
    size.try_into()
        .map_err(|_| Error::InvalidMetadataSize { size })
}

pub(crate) fn from_metadata_size(size: usize) -> own::Value {
    i64::try_from(size).unwrap().into()
}

#[cfg(test)]
mod tests {
    use bytes::BytesMut;

    use super::*;

    #[test]
    fn id() {
        assert_eq!(
            crate::EXTENSIONS[usize::from(Metadata::ID)].name,
            "ut_metadata",
        );
    }

    #[test]
    fn num_pieces() {
        assert_eq!(Metadata::num_pieces(0), 0);
        assert_eq!(Metadata::num_pieces(1), 1);
        assert_eq!(Metadata::num_pieces(16383), 1);
        assert_eq!(Metadata::num_pieces(16384), 1);
        assert_eq!(Metadata::num_pieces(16385), 2);
    }

    #[test]
    fn byte_range() {
        assert_eq!(Metadata::byte_range(0, 1), 0..1);
        assert_eq!(Metadata::byte_range(0, 2), 0..2);
        assert_eq!(Metadata::byte_range(0, 16384), 0..16384);

        assert_eq!(Metadata::byte_range(0, 16385), 0..16384);
        assert_eq!(Metadata::byte_range(1, 16385), 16384..16385);
    }

    #[test]
    fn conversion() {
        fn test(testdata: &[u8], expect: Metadata) {
            let mut buffer = BytesMut::new();
            expect.encode(&mut buffer);
            assert_eq!(buffer, testdata);

            assert_eq!(Metadata::decode(testdata), Ok(expect));
        }

        test(
            b"d8:msg_typei0e5:piecei42ee",
            Metadata::Request(Request::new(42)),
        );
        test(
            b"d3:foo3:bar8:msg_typei0e5:piecei42ee",
            Metadata::Request(Request {
                piece: 42,
                extra: BTreeMap::from([(
                    b"foo".as_slice(),
                    borrow::Value::new_byte_string(b"bar"),
                )]),
            }),
        );

        test(
            b"d8:msg_typei1e5:piecei42e10:total_sizei43eehello world",
            Metadata::Data(Data::new(42, Some(43), b"hello world")),
        );
        test(
            b"d8:msg_typei1e5:piecei42ee",
            Metadata::Data(Data::new(42, None, b"")),
        );

        test(
            b"d8:msg_typei2e5:piecei42ee",
            Metadata::Reject(Reject::new(42)),
        );

        assert_eq!(
            Metadata::try_from((
                BTreeMap::from([(b"msg_type".as_slice(), (-1).into())]).into(),
                b"".as_slice(),
            )),
            Err(Error::UnknownMetadataMessageType { message_type: -1 }),
        );
    }

    #[test]
    fn piece() {
        assert_eq!(to_piece(0), Ok(0));
        assert_eq!(to_piece(42), Ok(42));
        assert_eq!(to_piece(-1), Err(Error::InvalidMetadataPiece { piece: -1 }));

        assert_eq!(from_piece(0), 0.into());
        assert_eq!(from_piece(42), 42.into());
    }

    #[test]
    fn metadata_size() {
        assert_eq!(to_metadata_size(0), Ok(0));
        assert_eq!(to_metadata_size(42), Ok(42));
        assert_eq!(
            to_metadata_size(-1),
            Err(Error::InvalidMetadataSize { size: -1 }),
        );

        assert_eq!(from_metadata_size(0), 0.into());
        assert_eq!(from_metadata_size(42), 42.into());
    }
}
