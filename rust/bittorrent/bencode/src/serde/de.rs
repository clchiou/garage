use std::collections::btree_map;
use std::iter::Peekable;
use std::slice;
use std::str;

use serde::{
    de::{
        self, DeserializeSeed, EnumAccess, IntoDeserializer, MapAccess, SeqAccess, VariantAccess,
        Visitor,
    },
    Deserialize,
};
use snafu::prelude::*;

use g1_serde::{deserialize, deserialize_for_each};

use crate::borrow::{ByteString, Dictionary, List, Value};

use super::{
    error::{DecodeSnafu, Error, InvalidDictionaryAsEnumSnafu, InvalidListAsTypeSnafu},
    to_int,
};

pub struct Deserializer<'de>(&'de [u8]);

struct ListIter<'de, 'a>(slice::Iter<'a, Value<'de>>);
struct DictIter<'de, 'a>(Peekable<btree_map::Iter<'a, ByteString<'de>, Value<'de>>>);

pub fn from_bytes<'de, T>(buffer: &'de [u8]) -> Result<T, Error>
where
    T: Deserialize<'de>,
{
    T::deserialize(Deserializer::from_bytes(buffer))
}

impl<'de> Deserializer<'de> {
    pub fn from_bytes(buffer: &'de [u8]) -> Self {
        Self(buffer)
    }

    fn to_value(&self) -> Result<Value<'de>, Error> {
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

impl<'de, 'a> de::Deserializer<'de> for &'a Deserializer<'de> {
    type Error = Error;

    deserialize_for_each!(forward_to_value);
}

impl<'de, 'a> de::Deserializer<'de> for &'a mut Deserializer<'de> {
    type Error = Error;

    deserialize_for_each!(forward_to_value);
}

impl<'de> de::Deserializer<'de> for Deserializer<'de> {
    type Error = Error;

    deserialize_for_each!(forward_to_value);
}

impl<'de, 'a> ListIter<'de, 'a> {
    fn new(list: &'a List<'de>) -> Self {
        Self(list.iter())
    }
}

impl<'de, 'a> DictIter<'de, 'a> {
    fn new(dict: &'a Dictionary<'de>) -> Self {
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

impl<'de, 'a> de::Deserializer<'de> for &'a Value<'de> {
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

    deserialize!(newtype_struct(self, _name, visitor) visitor.visit_newtype_struct(self));

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

impl<'de, 'a> SeqAccess<'de> for ListIter<'de, 'a> {
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
        Some(self.0.len())
    }
}

impl<'de, 'a> MapAccess<'de> for DictIter<'de, 'a> {
    type Error = Error;

    fn next_key_seed<K>(&mut self, key_seed: K) -> Result<Option<K::Value>, Self::Error>
    where
        K: DeserializeSeed<'de>,
    {
        self.0
            .peek()
            .map(|(key, _)| key_seed.deserialize(&Value::ByteString(key)))
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
                    key_seed.deserialize(&Value::ByteString(key))?,
                    value_seed.deserialize(value)?,
                ))
            })
            .transpose()
    }

    fn size_hint(&self) -> Option<usize> {
        Some(self.0.len())
    }
}

impl<'de, 'a> EnumAccess<'de> for DictIter<'de, 'a> {
    type Error = Error;
    type Variant = &'a Value<'de>;

    fn variant_seed<V>(mut self, seed: V) -> Result<(V::Value, Self::Variant), Self::Error>
    where
        V: DeserializeSeed<'de>,
    {
        let (key, value) = self.0.next().unwrap();
        assert_eq!(self.0.next(), None);
        Ok((seed.deserialize(&Value::ByteString(key))?, value))
    }
}

impl<'de, 'a> VariantAccess<'de> for &'a Value<'de> {
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
