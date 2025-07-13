pub mod ser;

pub(crate) mod de;
pub(crate) mod de_impl;

mod int;
mod ser_impl;

use std::collections::{BTreeMap, btree_map};
use std::fmt;
use std::vec;

use g1_base::fmt::EscapeAscii;

use crate::bstr::OwnedBStr;

#[derive(Clone, Eq, Hash, PartialEq)]
pub enum Value<B> {
    ByteString(B),
    Integer(Integer),
    List(List<B>),
    Dictionary(Dictionary<B>),
}

// BEP 3 specifies integers as having unlimited precision.  For practical reasons, we restrict them
// to 64 bits instead of fully complying with BEP 3.
pub type Integer = i64;

pub type List<B> = Vec<Value<B>>;
pub type ListIter<B> = vec::IntoIter<Value<B>>;

// Use `BTreeMap` because BEP 3 requires dictionary keys to be sorted.
pub type Dictionary<B> = BTreeMap<B, Value<B>>;
pub type DictionaryIter<B> = btree_map::IntoIter<B, Value<B>>;

impl<B> fmt::Debug for Value<B>
where
    B: AsRef<[u8]>,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ByteString(bytes) => f
                .debug_tuple("ByteString")
                .field(&EscapeAscii(bytes.as_ref()))
                .finish(),
            Self::Integer(integer) => f.debug_tuple("Integer").field(integer).finish(),
            Self::List(list) => f.debug_tuple("List").field(list).finish(),
            Self::Dictionary(dict) => f
                .debug_tuple("Dictionary")
                .field_with(|f| {
                    f.debug_map()
                        .entries(dict.iter().map(|(k, v)| (EscapeAscii(k.as_ref()), v)))
                        .finish()
                })
                .finish(),
        }
    }
}

//
// Due to Rust's orphan rule, we cannot implement this:
// ```
// impl<B> TryFrom<Value<B>> for B { ... }
// ```
// We have to implement it for each concrete `B` type instead.
//

impl<B> TryFrom<Value<B>> for Integer {
    type Error = Value<B>;

    fn try_from(value: Value<B>) -> Result<Self, Self::Error> {
        match value {
            Value::Integer(integer) => Ok(integer),
            _ => Err(value),
        }
    }
}

impl<B> TryFrom<Value<B>> for List<B> {
    type Error = Value<B>;

    fn try_from(value: Value<B>) -> Result<Self, Self::Error> {
        match value {
            Value::List(list) => Ok(list),
            _ => Err(value),
        }
    }
}

impl<B> TryFrom<Value<B>> for Dictionary<B> {
    type Error = Value<B>;

    fn try_from(value: Value<B>) -> Result<Self, Self::Error> {
        match value {
            Value::Dictionary(dict) => Ok(dict),
            _ => Err(value),
        }
    }
}

impl<B> Value<B>
where
    B: AsRef<[u8]>,
{
    pub fn as_byte_string(&self) -> Option<&[u8]> {
        match self {
            Self::ByteString(bytes) => Some(bytes.as_ref()),
            _ => None,
        }
    }

    pub fn as_byte_string_mut(&mut self) -> Option<&mut B> {
        match self {
            Self::ByteString(bytes) => Some(bytes),
            _ => None,
        }
    }

    pub fn as_integer(&self) -> Option<Integer> {
        match self {
            Self::Integer(integer) => Some(*integer),
            _ => None,
        }
    }

    pub fn as_integer_mut(&mut self) -> Option<&mut Integer> {
        match self {
            Self::Integer(integer) => Some(integer),
            _ => None,
        }
    }

    pub fn as_list(&self) -> Option<&[Self]> {
        match self {
            Self::List(list) => Some(list),
            _ => None,
        }
    }

    pub fn as_list_mut(&mut self) -> Option<&mut List<B>> {
        match self {
            Self::List(list) => Some(list),
            _ => None,
        }
    }

    pub fn as_dictionary(&self) -> Option<&Dictionary<B>> {
        match self {
            Self::Dictionary(dict) => Some(dict),
            _ => None,
        }
    }

    pub fn as_dictionary_mut(&mut self) -> Option<&mut Dictionary<B>> {
        match self {
            Self::Dictionary(dict) => Some(dict),
            _ => None,
        }
    }
}

impl<B> From<Value<&'_ [u8]>> for Value<B>
where
    B: OwnedBStr,
{
    fn from(value: Value<&'_ [u8]>) -> Self {
        value.to_own()
    }
}

impl Value<&'_ [u8]> {
    // We cannot implement `ToOwned` for `Value` unless we change `B` from `&[u8]` to `[u8]`.  It
    // seems like a good idea to avoid using the same name `to_owned`.
    pub fn to_own<B>(&self) -> Value<B>
    where
        B: OwnedBStr,
    {
        match self {
            Self::ByteString(bytes) => Value::ByteString(B::from_bytes(bytes)),
            Self::Integer(integer) => Value::Integer(*integer),
            Self::List(list) => Value::List(list.iter().map(|e| e.to_own()).collect()),
            Self::Dictionary(dict) => Value::Dictionary(
                dict.iter()
                    .map(|(k, v)| (B::from_bytes(k), v.to_own()))
                    .collect(),
            ),
        }
    }
}
