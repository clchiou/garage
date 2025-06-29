use serde::de::{self, DeserializeSeed, Deserializer, MapAccess, SeqAccess, Visitor};

use crate::bstr::{DeserializableBStr, OwnedBStr};
use crate::error::Error;
use crate::value::{DictionaryIter, ListIter, Value};

use super::Json;

impl<'de, B> Deserializer<'de> for Json<Value<B>>
where
    B: DeserializableBStr<'de>,
    B: BStrToJson<'de>,
{
    type Error = Error;

    fn deserialize_any<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        match self.0 {
            Value::ByteString(bytes) => bytes.apply_visit_str(visitor),
            Value::Integer(integer) => visitor.visit_i64(integer),
            Value::List(list) => visitor.visit_seq(Json(list.into_iter())),
            Value::Dictionary(dict) => visitor.visit_map(Json((dict.into_iter(), None))),
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

impl<'de, B> SeqAccess<'de> for Json<ListIter<B>>
where
    B: DeserializableBStr<'de>,
    B: BStrToJson<'de>,
{
    type Error = Error;

    fn next_element_seed<T>(&mut self, seed: T) -> Result<Option<T::Value>, Self::Error>
    where
        T: DeserializeSeed<'de>,
    {
        self.0
            .next()
            .map(|value| seed.deserialize(Json(value)))
            .transpose()
    }

    fn size_hint(&self) -> Option<usize> {
        Some(self.0.len())
    }
}

impl<'de, B> MapAccess<'de> for Json<(DictionaryIter<B>, Option<Value<B>>)>
where
    B: DeserializableBStr<'de>,
    B: BStrToJson<'de>,
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
                seed.deserialize(Json(Value::ByteString(key)))
                    .inspect(|_| self.0.1 = Some(value))
            })
            .transpose()
    }

    fn next_value_seed<V>(&mut self, seed: V) -> Result<V::Value, Self::Error>
    where
        V: DeserializeSeed<'de>,
    {
        seed.deserialize(Json(self.0.1.take().expect("map value")))
    }

    fn size_hint(&self) -> Option<usize> {
        Some(self.0.0.len())
    }
}

trait BStrToJson<'de> {
    // Converts `self` to string and then invokes either `visit_string` or `visit_borrowed_str`.
    fn apply_visit_str<V, E>(self, visitor: V) -> Result<V::Value, E>
    where
        V: Visitor<'de>,
        E: de::Error;
}

impl<'de, B> BStrToJson<'de> for B
where
    B: OwnedBStr,
{
    fn apply_visit_str<V, E>(self, visitor: V) -> Result<V::Value, E>
    where
        V: de::Visitor<'de>,
        E: de::Error,
    {
        visitor.visit_string(
            String::from_utf8(self.into_byte_buf())
                .unwrap_or_else(|error| escape(error.as_bytes())),
        )
    }
}

impl<'de> BStrToJson<'de> for &'de [u8] {
    fn apply_visit_str<V, E>(self, visitor: V) -> Result<V::Value, E>
    where
        V: de::Visitor<'de>,
        E: de::Error,
    {
        match str::from_utf8(self) {
            Ok(string) => visitor.visit_borrowed_str(string),
            Err(_) => visitor.visit_string(escape(self)),
        }
    }
}

fn escape(bytes: &[u8]) -> String {
    bytes.escape_ascii().to_string()
}

#[cfg(test)]
mod tests {
    use bytes::Bytes;
    use serde::de::Deserialize;

    use crate::testing::{BENCODE, REDUCED_JSON};

    use super::*;

    #[test]
    fn from_bencode() {
        assert_eq!(
            serde_json::Value::deserialize(Json(BENCODE.clone())),
            Ok(REDUCED_JSON.clone()),
        );
        assert_eq!(
            serde_json::Value::deserialize(Json(BENCODE.to_own::<Bytes>())),
            Ok(REDUCED_JSON.clone()),
        );
    }
}
