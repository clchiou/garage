//! `Value` to/from Domain Object Type Converters
//!
//! Generally, `to_foo` converts `borrow::Value` to `Foo`, and `from_foo` converts `Foo` to
//! `own::Value`.

use std::str;

use chrono::{DateTime, TimeZone, Utc};
use snafu::prelude::*;

use bittorrent_base::PIECE_HASH_SIZE;
use bittorrent_bencode::{borrow, own};

use crate::{Error, InvalidNodeSnafu, InvalidPieceHashSizeSnafu};

pub(super) fn to_str(value: borrow::Value) -> Result<&str, Error> {
    let bytes = value
        .as_byte_string()
        .ok_or_else(|| Error::ExpectByteString {
            value: value.to_owned(),
        })?;
    str::from_utf8(bytes).map_err(|_| Error::InvalidUtf8String {
        string: bytes.escape_ascii().to_string(),
    })
}

pub(super) fn from_str(string: &str) -> own::Value {
    own::ByteString::from(string.as_bytes()).into()
}

pub(super) fn to_int(value: borrow::Value) -> Result<i64, Error> {
    value.as_integer().ok_or_else(|| Error::ExpectInteger {
        value: value.to_owned(),
    })
}

pub(super) fn to_timestamp(timestamp: i64) -> Result<DateTime<Utc>, Error> {
    Utc.timestamp_opt(timestamp, 0)
        .single()
        .ok_or(Error::InvalidTimestamp { timestamp })
}

pub(super) fn from_timestamp(timestamp: DateTime<Utc>) -> own::Value {
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

pub(super) fn to_vec<'a, T, F>(value: borrow::Value<'a>, convert: F) -> Result<Vec<T>, Error>
where
    T: 'a,
    F: Fn(borrow::Value<'a>) -> Result<T, Error>,
{
    value
        .into_list()
        .map_err(|value| Error::ExpectList {
            value: value.to_owned(),
        })?
        .0
        .into_iter()
        .map(convert)
        .try_collect()
}

pub(super) fn from_vec<T, F>(vec: Vec<T>, convert: F) -> own::Value
where
    F: Fn(T) -> own::Value,
{
    vec.into_iter()
        .map(convert)
        .collect::<Vec<own::Value>>()
        .into()
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
    let port = to_int(node.pop().unwrap())?;
    let port = u16::try_from(port).map_err(|_| Error::InvalidPort { port })?;
    let host = to_str(node.pop().unwrap())?;
    Ok((host, port))
}

pub(super) fn from_node((host, port): (&str, u16)) -> own::Value {
    vec![from_str(host), i64::from(port).into()].into()
}

pub(super) fn to_url_list(value: borrow::Value) -> Result<Vec<&str>, Error> {
    match value.into_list() {
        Ok((list, _)) => list.into_iter().map(to_str).try_collect(),
        Err(value) => Ok(vec![to_str(value)?]),
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

        // str
        ok(new_bytes(b"foo"), "foo", to_str, from_str);
        err(
            0.into(),
            Error::ExpectByteString { value: 0.into() },
            to_str,
        );
        err(
            new_bytes(b"2:\xc3\x28"),
            Error::InvalidUtf8String {
                string: b"2:\xc3\x28".escape_ascii().to_string(),
            },
            to_str,
        );

        // int
        ok(100.into(), 100, to_int, own::Value::from);
        err(
            new_bytes(b""),
            Error::ExpectInteger {
                value: new_owned_bytes(b""),
            },
            to_int,
        );

        // timestamp
        ok(
            100.into(),
            Utc.timestamp_opt(100, 0).single().unwrap(),
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

        // vec
        ok(
            vec![new_bytes(b"foo")].into(),
            vec!["foo"],
            |list| to_vec(list, to_str),
            |vec| from_vec(vec, from_str),
        );
        err(
            new_bytes(b"foo"),
            Error::ExpectList {
                value: new_owned_bytes(b"foo"),
            },
            |list| to_vec(list, to_str),
        );
        err(
            vec![new_bytes(b"foo"), 0.into()].into(),
            Error::ExpectByteString { value: 0.into() },
            |list| to_vec(list, to_str),
        );

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
