//! `Value` to/from Domain Object Type Converters
//!
//! Generally, `to_foo` converts `borrow::Value` to `Foo`, and `from_foo` converts `Foo` to
//! `own::Value`.

use std::collections::BTreeMap;
use std::str;

use snafu::prelude::*;

use crate::{borrow, own};

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

    #[snafu(display("invalid utf8 string: \"{string}\""))]
    InvalidUtf8String { string: String },
}

pub fn to_bytes<E>(value: borrow::Value) -> Result<&[u8], E>
where
    E: From<Error>,
{
    Ok(value
        .into_byte_string()
        .map_err(|value| Error::ExpectByteString {
            value: value.to_owned(),
        })?)
}

pub fn from_bytes(bytes: &[u8]) -> own::Value {
    own::ByteString::from(bytes).into()
}

pub fn to_str<E>(value: borrow::Value) -> Result<&str, E>
where
    E: From<Error>,
{
    let bytes = to_bytes(value)?;
    Ok(str::from_utf8(bytes).map_err(|_| Error::InvalidUtf8String {
        string: bytes.escape_ascii().to_string(),
    })?)
}

pub fn from_str(string: &str) -> own::Value {
    own::ByteString::from(string.as_bytes()).into()
}

pub fn to_int<E>(value: borrow::Value) -> Result<i64, E>
where
    E: From<Error>,
{
    Ok(value.as_integer().ok_or_else(|| Error::ExpectInteger {
        value: value.to_owned(),
    })?)
}

pub fn to_vec<'a, T, E, F>(value: borrow::Value<'a>, convert: F) -> Result<Vec<T>, E>
where
    T: 'a,
    E: From<Error>,
    F: Fn(borrow::Value<'a>) -> Result<T, E>,
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

pub fn from_vec<T, F>(vec: Vec<T>, convert: F) -> own::Value
where
    F: Fn(T) -> own::Value,
{
    vec.into_iter()
        .map(convert)
        .collect::<Vec<own::Value>>()
        .into()
}

#[allow(clippy::type_complexity)]
pub fn to_dict<E>(
    value: borrow::Value,
) -> Result<(BTreeMap<&[u8], borrow::Value>, Option<&[u8]>), E>
where
    E: From<Error>,
{
    Ok(value
        .into_dictionary()
        .map_err(|value| Error::ExpectDictionary {
            value: value.to_owned(),
        })?)
}

pub fn from_dict<'a, K, KF>(
    dict: BTreeMap<&'a [u8], borrow::Value<'a>>,
    convert: KF,
) -> BTreeMap<K, own::Value>
where
    K: Ord + 'a,
    KF: Fn(&'a [u8]) -> K,
{
    dict.into_iter()
        .map(|(key, value)| (convert(key), value.to_owned()))
        .collect::<BTreeMap<K, own::Value>>()
}

#[cfg(test)]
mod tests {
    use std::fmt;

    use super::*;

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

        // bytes
        ok(new_bytes(b"foo"), b"foo".as_slice(), to_bytes, from_bytes);
        err(
            0.into(),
            Error::ExpectByteString { value: 0.into() },
            to_bytes,
        );

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
                value: from_bytes(b""),
            },
            to_int,
        );

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
                value: from_bytes(b"foo"),
            },
            |list| to_vec(list, to_str),
        );
        err(
            vec![new_bytes(b"foo"), 0.into()].into(),
            Error::ExpectByteString { value: 0.into() },
            |list| to_vec(list, to_str),
        );

        // dict
        ok(
            BTreeMap::from([(b"foo".as_slice(), new_bytes(b"bar"))]).into(),
            BTreeMap::from([(b"foo".as_slice(), new_bytes(b"bar"))]),
            |dict| to_dict(dict).map(|(d, _)| d),
            |dict| from_dict(dict, own::ByteString::from).into(),
        );
        err(
            new_bytes(b"foo"),
            Error::ExpectDictionary {
                value: from_bytes(b"foo"),
            },
            |dict| to_dict(dict).map(|(d, _)| d),
        );
    }
}
