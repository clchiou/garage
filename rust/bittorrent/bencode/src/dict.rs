//! `Dictionary` to/from Domain Object Type Converters

use std::collections::BTreeMap;

use serde_bytes::Bytes;
use snafu::prelude::*;

use crate::{borrow, convert, own};

pub trait DictionaryRemove<'a>
where
    Self: 'a,
{
    fn must_remove<E>(&mut self, key: &[u8]) -> Result<borrow::Value<'a>, E>
    where
        E: From<Error>;

    fn remove_str<E>(&mut self, key: &[u8]) -> Result<Option<&'a str>, E>
    where
        E: From<convert::Error>;

    fn remove_int<E>(&mut self, key: &[u8]) -> Result<Option<i64>, E>
    where
        E: From<convert::Error>;
}

pub trait DictionaryInsert<'a>
where
    Self: 'a,
{
    fn insert_from<V, F>(&mut self, key: &'a [u8], value: Option<V>, convert: F)
    where
        F: FnOnce(V) -> own::Value;
}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Error {
    #[snafu(display("missing dictionary key: \"{key}\""))]
    MissingDictionaryKey { key: String },
}

impl<'a> DictionaryRemove<'a> for BTreeMap<&'a [u8], borrow::Value<'a>> {
    fn must_remove<E>(&mut self, key: &[u8]) -> Result<borrow::Value<'a>, E>
    where
        E: From<Error>,
    {
        Ok(self
            .remove(key)
            .ok_or_else(|| Error::MissingDictionaryKey {
                key: key.escape_ascii().to_string(),
            })?)
    }

    fn remove_str<E>(&mut self, key: &[u8]) -> Result<Option<&'a str>, E>
    where
        E: From<convert::Error>,
    {
        self.remove(key).map(convert::to_str).transpose()
    }

    fn remove_int<E>(&mut self, key: &[u8]) -> Result<Option<i64>, E>
    where
        E: From<convert::Error>,
    {
        self.remove(key).map(convert::to_int).transpose()
    }
}

impl<'a> DictionaryInsert<'a> for BTreeMap<own::ByteString, own::Value>
where
    Self: 'a,
{
    fn insert_from<V, F>(&mut self, key: &'a [u8], value: Option<V>, convert: F)
    where
        F: FnOnce(V) -> own::Value,
    {
        if let Some(value) = value {
            self.insert(own::ByteString::from(key), convert(value));
        }
    }
}

impl<'a> DictionaryInsert<'a> for BTreeMap<&'a Bytes, own::Value>
where
    Self: 'a,
{
    fn insert_from<V, F>(&mut self, key: &'a [u8], value: Option<V>, convert: F)
    where
        F: FnOnce(V) -> own::Value,
    {
        if let Some(value) = value {
            self.insert(Bytes::new(key), convert(value));
        }
    }
}
