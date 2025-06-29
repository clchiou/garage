use std::marker::PhantomData;

use serde::de::value::BorrowedStrDeserializer;
use serde::de::{
    self, DeserializeSeed, Deserializer, EnumAccess, IntoDeserializer, MapAccess, SeqAccess,
    Unexpected, VariantAccess, Visitor,
};

use crate::bstr::{DeserializableBStr, OwnedBStr};
use crate::error::Error;
use crate::value::{DictionaryIter, ListIter, Value};

use super::{BYTES_TAG, Yaml};

impl<'de, B> Deserializer<'de> for Yaml<Value<B>>
where
    B: DeserializableBStr<'de>,
    B: BStrToYaml<'de>,
{
    type Error = Error;

    fn deserialize_any<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        match self.0 {
            Value::ByteString(bytes) => bytes.apply_visit_str(visitor),
            Value::Integer(integer) => visitor.visit_i64(integer),
            Value::List(list) => visitor.visit_seq(Yaml(list.into_iter())),
            Value::Dictionary(dict) => visitor.visit_map(Yaml((dict.into_iter(), None))),
        }
    }

    fn deserialize_ignored_any<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        visitor.visit_unit()
    }

    serde::forward_to_deserialize_any! {
        bool
        i8 i16 i32 i64 i128
        u8 u16 u32 u64 u128
        f32 f64
        char str string
        bytes byte_buf
        option
        unit unit_struct
        newtype_struct
        seq tuple tuple_struct
        map struct
        enum
        identifier
    }
}

impl<'de, B> SeqAccess<'de> for Yaml<ListIter<B>>
where
    B: DeserializableBStr<'de>,
    B: BStrToYaml<'de>,
{
    type Error = Error;

    fn next_element_seed<T>(&mut self, seed: T) -> Result<Option<T::Value>, Self::Error>
    where
        T: DeserializeSeed<'de>,
    {
        self.0
            .next()
            .map(|value| seed.deserialize(Yaml(value)))
            .transpose()
    }

    fn size_hint(&self) -> Option<usize> {
        Some(self.0.len())
    }
}

impl<'de, B> MapAccess<'de> for Yaml<(DictionaryIter<B>, Option<Value<B>>)>
where
    B: DeserializableBStr<'de>,
    B: BStrToYaml<'de>,
{
    type Error = Error;

    fn next_key_seed<K>(&mut self, seed: K) -> Result<Option<K::Value>, Self::Error>
    where
        K: DeserializeSeed<'de>,
    {
        self.0
            .0
            .next()
            .map(|(key, value)| {
                seed.deserialize(Yaml(Value::ByteString(key)))
                    .inspect(|_| self.0.1 = Some(value))
            })
            .transpose()
    }

    fn next_value_seed<V>(&mut self, seed: V) -> Result<V::Value, Self::Error>
    where
        V: DeserializeSeed<'de>,
    {
        seed.deserialize(Yaml(self.0.1.take().expect("map value")))
    }

    fn size_hint(&self) -> Option<usize> {
        Some(self.0.0.len())
    }
}

trait BStrToYaml<'de> {
    // Converts `self` to string and then invokes either `visit_string`, `visit_borrowed_str`, or
    // `visit_enum`.
    fn apply_visit_str<V, E>(self, visitor: V) -> Result<V::Value, E>
    where
        V: Visitor<'de>,
        E: de::Error;
}

impl<'de, B> BStrToYaml<'de> for B
where
    B: OwnedBStr,
{
    fn apply_visit_str<V, E>(self, visitor: V) -> Result<V::Value, E>
    where
        V: de::Visitor<'de>,
        E: de::Error,
    {
        match String::from_utf8(self.into_byte_buf()) {
            Ok(string) => visitor.visit_string(string),
            Err(error) => visitor.visit_enum(BytesDeserializer::new(error.as_bytes())),
        }
    }
}

impl<'de> BStrToYaml<'de> for &'de [u8] {
    fn apply_visit_str<V, E>(self, visitor: V) -> Result<V::Value, E>
    where
        V: de::Visitor<'de>,
        E: de::Error,
    {
        match str::from_utf8(self) {
            Ok(string) => visitor.visit_borrowed_str(string),
            Err(_) => visitor.visit_enum(BytesDeserializer::new(self)),
        }
    }
}

struct BytesDeserializer<'a, E>(&'a [u8], PhantomData<E>);

impl<'a, E> BytesDeserializer<'a, E> {
    fn new(bytes: &'a [u8]) -> Self {
        Self(bytes, PhantomData)
    }
}

impl<'de, E> EnumAccess<'de> for BytesDeserializer<'_, E>
where
    E: de::Error,
{
    type Error = E;
    type Variant = Self;

    fn variant_seed<V>(self, seed: V) -> Result<(V::Value, Self::Variant), Self::Error>
    where
        V: DeserializeSeed<'de>,
    {
        Ok((
            seed.deserialize(BorrowedStrDeserializer::new(BYTES_TAG))?,
            self,
        ))
    }
}

impl<'de, E> VariantAccess<'de> for BytesDeserializer<'_, E>
where
    E: de::Error,
{
    type Error = E;

    fn unit_variant(self) -> Result<(), Self::Error> {
        Err(E::invalid_type(Unexpected::NewtypeVariant, &"unit variant"))
    }

    fn newtype_variant_seed<T>(self, seed: T) -> Result<T::Value, Self::Error>
    where
        T: DeserializeSeed<'de>,
    {
        seed.deserialize(self.0.escape_ascii().to_string().into_deserializer())
    }

    fn tuple_variant<V>(self, _len: usize, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        Err(E::invalid_type(Unexpected::NewtypeVariant, &visitor))
    }

    fn struct_variant<V>(
        self,
        _fields: &'static [&'static str],
        visitor: V,
    ) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        Err(E::invalid_type(Unexpected::NewtypeVariant, &visitor))
    }
}

#[cfg(test)]
mod tests {
    use bytes::Bytes;
    use serde::de::Deserialize;

    use crate::testing::{BENCODE, REDUCED_YAML};

    use super::*;

    #[test]
    fn from_bencode() {
        assert_eq!(
            serde_yaml::Value::deserialize(Yaml(BENCODE.clone())),
            Ok(REDUCED_YAML.clone()),
        );
        assert_eq!(
            serde_yaml::Value::deserialize(Yaml(BENCODE.to_own::<Bytes>())),
            Ok(REDUCED_YAML.clone()),
        );
    }
}
