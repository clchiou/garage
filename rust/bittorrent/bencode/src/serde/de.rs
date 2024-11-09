use std::collections::{btree_map, BTreeMap};
use std::fmt;
use std::iter::Peekable;
use std::slice;
use std::str;

use serde::{
    de::{
        self, DeserializeSeed, EnumAccess, Error as _, IntoDeserializer, MapAccess, SeqAccess,
        VariantAccess, Visitor,
    },
    Deserialize,
};
use snafu::prelude::*;

use g1_serde::{deserialize, deserialize_for_each};

use crate::{
    borrow::{ByteString, Dictionary, List, Value},
    own,
};

use super::{
    error::{DecodeSnafu, Error, InvalidDictionaryAsEnumSnafu, InvalidListAsTypeSnafu},
    to_int,
};

//
// Deserialize
//

// Magic strings that do not collide with any legitimate type name.
const BORROWED_VALUE_VISITOR: &str = "$bittorrent_bencode::serde::private::BorrowedValueVisitor";
const RAW_VALUE_VISITOR: &str = "$bittorrent_bencode::serde::private::RawValueVisitor";

struct OwnedValueVisitor;
struct BorrowedValueVisitor<const STRICT: bool>;
struct RawValueVisitor<const STRICT: bool>;

impl<'de> Deserialize<'de> for own::Value {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: de::Deserializer<'de>,
    {
        deserializer.deserialize_any(OwnedValueVisitor)
    }
}

impl<'de: 'a, 'a, const STRICT: bool> Deserialize<'de> for Value<'a, STRICT> {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: de::Deserializer<'de>,
    {
        deserializer.deserialize_newtype_struct(BORROWED_VALUE_VISITOR, BorrowedValueVisitor)
    }
}

// `own::Value` does not store the raw value; it can be deserialized without the need for the magic
// token trick.  Therefore, it can be used in combination with `#[serde(flatten)]`.
impl<'de> Visitor<'de> for OwnedValueVisitor {
    type Value = own::Value;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("any valid Bencode value")
    }

    fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(value.into())
    }

    fn visit_borrowed_bytes<E>(self, value: &'de [u8]) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(own::ByteString::from(value).into())
    }

    fn visit_seq<A>(self, mut seq: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut list = Vec::with_capacity(seq.size_hint().unwrap_or(0));
        while let Some(item) = seq.next_element()? {
            list.push(item);
        }
        Ok(list.into())
    }

    fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut dict = BTreeMap::new();
        while let Some((key, value)) = map.next_entry::<&[u8], own::Value>()? {
            dict.insert(own::ByteString::from(key), value);
        }
        Ok(dict.into())
    }
}

impl<'de, const STRICT: bool> Visitor<'de> for BorrowedValueVisitor<STRICT> {
    type Value = Value<'de, STRICT>;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("any valid Bencode value")
    }

    fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::Integer(value))
    }

    fn visit_borrowed_bytes<E>(self, value: &'de [u8]) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::ByteString(value))
    }

    fn visit_newtype_struct<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: de::Deserializer<'de>,
    {
        deserializer.deserialize_newtype_struct(RAW_VALUE_VISITOR, RawValueVisitor)
    }
}

impl<'de, const STRICT: bool> Visitor<'de> for RawValueVisitor<STRICT> {
    type Value = Value<'de, STRICT>;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("any valid Bencode raw value")
    }

    fn visit_borrowed_bytes<E>(self, value: &'de [u8]) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Value::try_from(value).map_err(|e| E::custom(e.to_string()))
    }
}

//
// Deserializer
//

pub struct Deserializer<'de, const STRICT: bool = true>(&'de [u8]);

struct ListIter<'de, 'a, const STRICT: bool>(slice::Iter<'a, Value<'de, STRICT>>);
struct DictIter<'de, 'a, const STRICT: bool>(
    Peekable<btree_map::Iter<'a, ByteString<'de>, Value<'de, STRICT>>>,
);

pub fn from_bytes<'de, T>(buffer: &'de [u8]) -> Result<T, Error>
where
    T: Deserialize<'de>,
{
    T::deserialize(Deserializer::from_bytes(buffer))
}

pub fn from_bytes_lenient<'de, T>(buffer: &'de [u8]) -> Result<T, Error>
where
    T: Deserialize<'de>,
{
    T::deserialize(Deserializer::from_bytes_lenient(buffer))
}

type TwoPassDict<'de, const STRICT: bool> = BTreeMap<&'de [u8], Value<'de, STRICT>>;

pub fn from_bytes_lenient_two_pass<'de, T, E>(buffer: &'de [u8]) -> Result<T, Error>
where
    T: TryFrom<TwoPassDict<'de, true>, Error = E>,
    E: fmt::Display,
{
    from_bytes_lenient::<TwoPassDict<false>>(buffer)?
        .into_iter()
        .map(|(key, value)| (key, value.to_strict()))
        .collect::<TwoPassDict<true>>()
        .try_into()
        .map_err(Error::custom)
}

impl<'de> Deserializer<'de> {
    pub fn from_bytes(buffer: &'de [u8]) -> Self {
        Self(buffer)
    }
}

impl<'de> Deserializer<'de, false> {
    pub fn from_bytes_lenient(buffer: &'de [u8]) -> Self {
        Self(buffer)
    }
}

impl<'de, const STRICT: bool> Deserializer<'de, STRICT> {
    fn to_value(&self) -> Result<Value<'de, STRICT>, Error> {
        Value::try_from(self.0).context(DecodeSnafu)
    }
}

macro_rules! forward_to_value {
    ($func_root:ident $($arg:ident)*) => {
        paste::paste! {
            deserialize!($func_root(self, $($arg, )* visitor) {
                self.to_value()?.[<deserialize_ $func_root>]($($arg, )* visitor)
            });
        }
    };
}

// We provide all possible implementations (`&Self`, `&mut Self`, and `Self`) that `Either` may
// require.

impl<'de, const STRICT: bool> de::Deserializer<'de> for &Deserializer<'de, STRICT> {
    type Error = Error;

    deserialize_for_each!(forward_to_value);
}

impl<'de, const STRICT: bool> de::Deserializer<'de> for &mut Deserializer<'de, STRICT> {
    type Error = Error;

    deserialize_for_each!(forward_to_value);
}

impl<'de, const STRICT: bool> de::Deserializer<'de> for Deserializer<'de, STRICT> {
    type Error = Error;

    deserialize_for_each!(forward_to_value);
}

impl<'de, 'a, const STRICT: bool> ListIter<'de, 'a, STRICT> {
    fn new(list: &'a List<'de, STRICT>) -> Self {
        Self(list.iter())
    }
}

impl<'de, 'a, const STRICT: bool> DictIter<'de, 'a, STRICT> {
    fn new(dict: &'a Dictionary<'de, STRICT>) -> Self {
        Self(dict.iter().peekable())
    }
}

/// Extracts the requested variant from a `borrow::Value` enum value.
macro_rules! as_ {
    ($value_type:ident, $value:expr) => {
        match $value {
            Value::$value_type(value) => Ok(value),
            value => {
                return Err(Error::ExpectValueType {
                    type_name: stringify!($value_type),
                    value: value.to_owned(),
                });
            }
        }
    };
}

macro_rules! deserialize_int {
    ($func_root:ident) => {
        deserialize_int!($func_root(value) to_int(*value));
    };
    ($func_root:ident($value:ident) $expr:expr) => {
        paste::paste! {
            deserialize!($func_root(self, visitor) {
                let $value = as_!(Integer, self)?;
                visitor.[<visit_ $func_root>]($expr?)
            });
        }
    };
}

macro_rules! deserialize_from_bytes {
    ($func_root:ident($value:ident) $expr:expr) => {
        paste::paste! {
            deserialize!($func_root(self, visitor) {
                let $value = as_!(ByteString, self)?;
                visitor.[<visit_ $func_root>]($expr?)
            });
        }
    };
}

fn to_str(value: &[u8]) -> Result<&str, Error> {
    str::from_utf8(value).map_err(|_| Error::InvalidUtf8String {
        string: value.escape_ascii().to_string(),
    })
}

impl<'de, const STRICT: bool> de::Deserializer<'de> for &Value<'de, STRICT> {
    type Error = Error;

    deserialize!(any(self, visitor) {
        match self {
            Value::ByteString(bytes) => visitor.visit_borrowed_bytes(bytes),
            Value::Integer(int) => visitor.visit_i64(*int),
            Value::List(list) => visitor.visit_seq(ListIter::new(list)),
            Value::Dictionary(dict) => visitor.visit_map(DictIter::new(dict)),
        }
    });

    deserialize_int!(bool(value) {
        match value {
            0 => Ok(false),
            1 => Ok(true),
            _ => Err(Error::IntegerValueOutOfRange),
        }
    });

    deserialize_int!(i8);
    deserialize_int!(i16);
    deserialize_int!(i32);
    deserialize!(i64(self, visitor) visitor.visit_i64(*as_!(Integer, self)?));

    deserialize_int!(u8);
    deserialize_int!(u16);
    deserialize_int!(u32);
    deserialize_int!(u64);

    serde::serde_if_integer128! {
        deserialize_int!(i128);
        deserialize_int!(u128);
    }

    deserialize_from_bytes!(f32(value) {
        Ok(f32::from_be_bytes(*<&[u8; 4]>::try_from(*value).map_err(
            |_| Error::InvalidFloatingPoint {
                value: value.to_vec(),
            },
        )?))
    });
    deserialize_from_bytes!(f64(value) {
        Ok(f64::from_be_bytes(*<&[u8; 8]>::try_from(*value).map_err(
            |_| Error::InvalidFloatingPoint {
                value: value.to_vec(),
            },
        )?))
    });

    deserialize_int!(char(value) { to_int(*value).map(u32::from_le).and_then(to_int) });

    deserialize!(str(self, visitor) visitor.visit_borrowed_str(to_str(as_!(ByteString, self)?)?));
    deserialize!(string => str);

    deserialize!(bytes(self, visitor) visitor.visit_borrowed_bytes(as_!(ByteString, self)?));
    deserialize!(byte_buf => bytes);

    deserialize!(option(self, visitor) {
        let list = as_!(List, self)?;
        ensure!(list.len() < 2, InvalidListAsTypeSnafu {
            type_name: "option",
            list: self.to_owned(),
        });
        if list.is_empty() {
            visitor.visit_none()
        } else {
            visitor.visit_some(list.first().unwrap())
        }
    });

    deserialize!(unit(self, visitor) {
        ensure!(as_!(List, self)?.is_empty(), InvalidListAsTypeSnafu {
            type_name: "unit",
            list: self.to_owned(),
        });
        visitor.visit_unit()
    });
    deserialize!(unit_struct => unit);

    deserialize!(newtype_struct(self, name, visitor) {
        match name {
            BORROWED_VALUE_VISITOR => match self {
                Value::ByteString(bytes) => visitor.visit_borrowed_bytes(bytes),
                Value::Integer(int) => visitor.visit_i64(*int),
                Value::List(_) | Value::Dictionary(_) => visitor.visit_newtype_struct(self),
            },
            RAW_VALUE_VISITOR => visitor.visit_borrowed_bytes(self.raw_value()),
            _ => visitor.visit_newtype_struct(self),
        }
    });

    deserialize!(seq(self, visitor) visitor.visit_seq(ListIter::new(as_!(List, self)?)));
    deserialize!(tuple => seq);
    deserialize!(tuple_struct => seq);

    deserialize!(map(self, visitor) visitor.visit_map(DictIter::new(as_!(Dictionary, self)?)));
    deserialize!(struct => map);

    deserialize!(enum(self, _name, _variants, visitor) {
        match self {
            Value::ByteString(bytes) => visitor.visit_enum(to_str(bytes)?.into_deserializer()),
            Value::Dictionary(dict) => {
                ensure!(
                    dict.len() == 1,
                    InvalidDictionaryAsEnumSnafu {
                        dict: self.to_owned(),
                    },
                );
                visitor.visit_enum(DictIter::new(dict))
            }
            value => Err(Error::ExpectValueType {
                type_name: "enum",
                value: value.to_owned(),
            }),
        }
    });

    deserialize!(identifier => str);

    deserialize!(ignored_any => any);
}

impl<'de, const STRICT: bool> SeqAccess<'de> for ListIter<'de, '_, STRICT> {
    type Error = Error;

    fn next_element_seed<T>(&mut self, seed: T) -> Result<Option<T::Value>, Self::Error>
    where
        T: DeserializeSeed<'de>,
    {
        self.0
            .next()
            .map(|value| seed.deserialize(value))
            .transpose()
    }

    fn size_hint(&self) -> Option<usize> {
        self.0.size_hint().1
    }
}

impl<'de, const STRICT: bool> MapAccess<'de> for DictIter<'de, '_, STRICT> {
    type Error = Error;

    fn next_key_seed<K>(&mut self, key_seed: K) -> Result<Option<K::Value>, Self::Error>
    where
        K: DeserializeSeed<'de>,
    {
        self.0
            .peek()
            .map(|(key, _)| key_seed.deserialize(&Value::<STRICT>::ByteString(key)))
            .transpose()
    }

    fn next_value_seed<V>(&mut self, value_seed: V) -> Result<V::Value, Self::Error>
    where
        V: DeserializeSeed<'de>,
    {
        self.0
            .next()
            .map(|(_, value)| value_seed.deserialize(value))
            .unwrap()
    }

    fn next_entry_seed<K, V>(
        &mut self,
        key_seed: K,
        value_seed: V,
    ) -> Result<Option<(K::Value, V::Value)>, Self::Error>
    where
        K: DeserializeSeed<'de>,
        V: DeserializeSeed<'de>,
    {
        self.0
            .next()
            .map(|(key, value)| {
                Ok((
                    key_seed.deserialize(&Value::<STRICT>::ByteString(key))?,
                    value_seed.deserialize(value)?,
                ))
            })
            .transpose()
    }

    fn size_hint(&self) -> Option<usize> {
        Some(self.0.len())
    }
}

impl<'de, 'a, const STRICT: bool> EnumAccess<'de> for DictIter<'de, 'a, STRICT> {
    type Error = Error;
    type Variant = &'a Value<'de, STRICT>;

    fn variant_seed<V>(mut self, seed: V) -> Result<(V::Value, Self::Variant), Self::Error>
    where
        V: DeserializeSeed<'de>,
    {
        let (key, value) = self.0.next().unwrap();
        assert_eq!(self.0.next(), None);
        Ok((seed.deserialize(&Value::<STRICT>::ByteString(key))?, value))
    }
}

impl<'de, const STRICT: bool> VariantAccess<'de> for &Value<'de, STRICT> {
    type Error = Error;

    fn unit_variant(self) -> Result<(), Self::Error> {
        panic!("expect a unit variant: {:?}", self);
    }

    fn newtype_variant_seed<T>(self, seed: T) -> Result<T::Value, Self::Error>
    where
        T: DeserializeSeed<'de>,
    {
        seed.deserialize(self)
    }

    fn tuple_variant<V>(self, _len: usize, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        de::Deserializer::deserialize_seq(self, visitor)
    }

    fn struct_variant<V>(
        self,
        _fields: &'static [&'static str],
        visitor: V,
    ) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        de::Deserializer::deserialize_map(self, visitor)
    }
}
