//! `Value` to/from Domain Object Type Converters
//!
//! Generally, `to_foo` converts `borrow::Value` to `Foo`, and `from_foo` converts `Foo` to
//! `own::Value`.

use snafu::prelude::*;

use g1_chrono::Timestamp;

use bittorrent_base::PIECE_HASH_SIZE;
use bittorrent_bencode::{
    borrow,
    convert::{self, from_str, from_vec, to_int, to_str, to_vec},
    dict, own,
};

use crate::{Error, InvalidNodeSnafu, InvalidPieceHashSizeSnafu};

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

//
// Yeah, the directions of the to/from timestamp are confusing here.
//

pub(super) fn to_timestamp(timestamp: i64) -> Result<Timestamp, Error> {
    Timestamp::from_timestamp(timestamp, 0).ok_or(Error::InvalidTimestamp { timestamp })
}

pub(super) fn from_timestamp(timestamp: Timestamp) -> own::Value {
    timestamp.timestamp().into()
}

pub(super) fn to_length(length: i64) -> Result<u64, Error> {
    length
        .try_into()
        .map_err(|_| Error::InvalidLength { length })
}

pub(super) fn from_length(length: u64) -> own::Value {
    i64::try_from(length).unwrap().into()
}

pub(super) fn to_private(private: i64) -> bool {
    // BEP 27 specifies "private=1" as true, but we consider any non-zero value to be true.
    private != 0
}

pub(super) fn from_private(private: bool) -> own::Value {
    i64::from(private).into()
}

pub(super) fn to_announce_list(value: borrow::Value) -> Result<Vec<Vec<&str>>, Error> {
    to_vec(value, |list| to_vec(list, to_str))
}

pub(super) fn from_announce_list(announce_list: Vec<Vec<&str>>) -> own::Value {
    from_vec(announce_list, |list| from_vec(list, from_str))
}

pub(super) fn to_nodes(value: borrow::Value) -> Result<Vec<(&str, u16)>, Error> {
    to_vec(value, to_node)
}

pub(super) fn from_nodes(nodes: Vec<(&str, u16)>) -> own::Value {
    from_vec(nodes, from_node)
}

pub(super) fn to_node(value: borrow::Value) -> Result<(&str, u16), Error> {
    let (mut node, _) = value.into_list().map_err(|value| Error::ExpectList {
        value: value.to_owned(),
    })?;
    ensure!(
        node.len() == 2,
        InvalidNodeSnafu {
            node: node
                .iter()
                .map(borrow::Value::to_owned)
                .collect::<Vec<own::Value>>(),
        }
    );
    let port = to_int::<Error>(node.pop().unwrap())?;
    let port = u16::try_from(port).map_err(|_| Error::InvalidPort { port })?;
    let host = to_str::<Error>(node.pop().unwrap())?;
    Ok((host, port))
}

pub(super) fn from_node((host, port): (&str, u16)) -> own::Value {
    vec![from_str(host), i64::from(port).into()].into()
}

pub(super) fn to_url_list(value: borrow::Value) -> Result<Vec<&str>, Error> {
    match value.into_list() {
        Ok((list, _)) => list.into_iter().map(to_str).try_collect(),
        Err(value) => Ok(vec![to_str::<Error>(value)?]),
    }
}

pub(super) fn from_url_list(url_list: Vec<&str>) -> own::Value {
    if url_list.len() == 1 {
        from_str(url_list[0])
    } else {
        from_vec(url_list, from_str)
    }
}

pub(super) fn to_pieces(value: borrow::Value) -> Result<Vec<&[u8]>, Error> {
    let bytes = value
        .as_byte_string()
        .ok_or_else(|| Error::ExpectByteString {
            value: value.to_owned(),
        })?;
    ensure!(
        bytes.len() % PIECE_HASH_SIZE == 0,
        InvalidPieceHashSizeSnafu { size: bytes.len() }
    );
    Ok(bytes.chunks_exact(PIECE_HASH_SIZE).collect())
}

pub(super) fn from_pieces(pieces: Vec<&[u8]>) -> own::Value {
    let mut bytes = own::ByteString::with_capacity(pieces.len() * PIECE_HASH_SIZE);
    pieces
        .iter()
        .for_each(|piece| bytes.extend_from_slice(piece));
    bytes.into()
}

#[cfg(test)]
mod tests {
    use std::fmt;

    use super::*;

    fn new_owned_bytes(bytes: &[u8]) -> own::Value {
        own::ByteString::from(bytes).into()
    }

    fn new_bytes(bytes: &[u8]) -> borrow::Value<'_> {
        borrow::Value::new_byte_string(bytes)
    }

    #[test]
    fn test() {
        fn ok<'a, T, ToFunc, FromFunc>(
            value: borrow::Value<'a>,
            expect: T,
            to_func: ToFunc,
            from_func: FromFunc,
        ) where
            T: Clone + fmt::Debug + PartialEq + 'a,
            ToFunc: Fn(borrow::Value<'a>) -> Result<T, Error>,
            FromFunc: Fn(T) -> own::Value,
        {
            let owned_value = value.to_owned();
            assert_eq!(to_func(value), Ok(expect.clone()));
            assert_eq!(from_func(expect), owned_value);
        }

        fn err<'a, T, ToFunc>(value: borrow::Value<'a>, expect: Error, to_func: ToFunc)
        where
            T: fmt::Debug + PartialEq + 'a,
            ToFunc: Fn(borrow::Value<'a>) -> Result<T, Error>,
        {
            assert_eq!(to_func(value), Err(expect));
        }

        // timestamp
        ok(
            100.into(),
            Timestamp::from_timestamp(100, 0).unwrap(),
            |value| to_int(value).and_then(to_timestamp),
            from_timestamp,
        );

        // length
        ok(
            42.into(),
            42,
            |value| to_int(value).and_then(to_length),
            from_length,
        );
        err((-1).into(), Error::InvalidLength { length: -1 }, |value| {
            to_int(value).and_then(to_length)
        });

        // announce_list
        ok(
            vec![vec![new_bytes(b"foo"), new_bytes(b"bar")].into()].into(),
            vec![vec!["foo", "bar"]],
            to_announce_list,
            from_announce_list,
        );

        // node
        ok(
            vec![new_bytes(b"foo"), 8000.into()].into(),
            ("foo", 8000),
            to_node,
            from_node,
        );
        err(
            vec![new_bytes(b"foo")].into(),
            Error::InvalidNode {
                node: vec![new_owned_bytes(b"foo")].into(),
            },
            to_node,
        );
        err(
            vec![new_bytes(b"foo"), 65536.into()].into(),
            Error::InvalidPort { port: 65536 },
            to_node,
        );

        // url_list
        ok(
            vec![].into(),
            Vec::<&str>::new(),
            to_url_list,
            from_url_list,
        );
        assert_eq!(to_url_list(vec![new_bytes(b"foo")].into()), Ok(vec!["foo"]));
        assert_eq!(from_url_list(vec!["foo"]), new_owned_bytes(b"foo"));
        ok(
            vec![new_bytes(b"foo"), new_bytes(b"bar")].into(),
            vec!["foo", "bar"],
            to_url_list,
            from_url_list,
        );
        ok(new_bytes(b"foo"), vec!["foo"], to_url_list, from_url_list);

        // pieces
        ok(new_bytes(b""), Vec::<&[u8]>::new(), to_pieces, from_pieces);
        ok(
            new_bytes(b"abcdefghijklmnopqrst"),
            vec![b"abcdefghijklmnopqrst".as_slice()],
            to_pieces,
            from_pieces,
        );
        ok(
            new_bytes(b"abcdefghijklmnopqrst01234567890123456789"),
            vec![
                b"abcdefghijklmnopqrst".as_slice(),
                b"01234567890123456789".as_slice(),
            ],
            to_pieces,
            from_pieces,
        );
        err(
            new_bytes(b"0"),
            Error::InvalidPieceHashSize { size: 1 },
            to_pieces,
        );
    }
}
