use std::fmt;
use std::marker::PhantomData;

use bytes::Bytes;
use serde::de::{self, DeserializeSeed, MapAccess, Visitor};

use crate::bstr::DeserializableBStr;
use crate::error::{self, Error};

use super::Deserializer;
use super::read::{ReadExt, Token};
use super::strict::Strictness;

pub(super) struct DictionaryDeserializer<'a, R, E, S> {
    deserializer: &'a mut Deserializer<R, E, S>,
    last_key: Option<Bytes>,
    _phantom: PhantomData<(E, S)>,
}

pub(super) struct KeyDeserializer<'b, 'a, R, E, S>(&'b mut DictionaryDeserializer<'a, R, E, S>);

impl<'a, R, E, S> DictionaryDeserializer<'a, R, E, S> {
    pub(super) fn new(deserializer: &'a mut Deserializer<R, E, S>) -> Self {
        Self {
            deserializer,
            last_key: None,
            _phantom: PhantomData,
        }
    }
}

impl<'b, 'a, R, E, S> KeyDeserializer<'b, 'a, R, E, S> {
    fn new(dict: &'b mut DictionaryDeserializer<'a, R, E, S>) -> Self {
        Self(dict)
    }
}

impl<'de, 'a, R, E, S> DictionaryDeserializer<'a, R, E, S>
where
    R: ReadExt<'de, S, E>,
    E: error::de::Error,
    S: Strictness,
{
    pub(super) fn deserialize_key(
        &mut self,
    ) -> Result<Option<KeyDeserializer<'_, 'a, R, E, S>>, E> {
        Ok(self.deserializer.deserialize_item_token()?.map(|token| {
            self.deserializer.undeserialize_token(token);
            KeyDeserializer::new(self)
        }))
    }

    pub(super) fn deserialize_value(&mut self) -> Result<&mut Deserializer<R, E, S>, E> {
        match self.deserializer.deserialize_item_token()? {
            Some(token) => {
                self.deserializer.undeserialize_token(token);
                Ok(self.deserializer)
            }
            None => Err(Error::MissingValue {
                key: self.last_key.clone().expect("dictionary key"),
            }
            .into()),
        }
    }

    // When the visitor is not expected to consume the entire dictionary (e.g., a enum visitor),
    // our `Deserializer` should invoke this after `visit_enum` returns.
    pub(super) fn deserialize_end(&mut self, expect_len: usize) -> Result<(), E> {
        match self.deserializer.deserialize_item_token()? {
            None => Ok(()),
            Some(_) => Err(E::custom(fmt::from_fn(|f| {
                std::write!(f, "invalid length of dictionary, expected {expect_len}")
            }))),
        }
    }
}

impl<'de, 'a, R, E, S> MapAccess<'de> for &mut DictionaryDeserializer<'a, R, E, S>
where
    R: ReadExt<'de, S, E>,
    E: error::de::Error,
    S: Strictness,
{
    type Error = E;

    fn next_key_seed<K>(&mut self, seed: K) -> Result<Option<K::Value>, Self::Error>
    where
        K: DeserializeSeed<'de>,
    {
        self.deserialize_key()?
            .map(|mut deserializer| seed.deserialize(&mut deserializer))
            .transpose()
    }

    fn next_value_seed<V>(&mut self, seed: V) -> Result<V::Value, Self::Error>
    where
        V: DeserializeSeed<'de>,
    {
        seed.deserialize(self.deserialize_value()?)
    }
}

impl<'de, 'b, 'a, R, E, S> de::Deserializer<'de> for &mut KeyDeserializer<'b, 'a, R, E, S>
where
    R: ReadExt<'de, S, E>,
    E: error::de::Error,
    S: Strictness,
{
    type Error = E;

    fn deserialize_any<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        match self.0.deserializer.deserialize_token()? {
            Token::ByteString(b0) => {
                let key = self.0.deserializer.reader.read_byte_string(b0)?;
                {
                    let key = Bytes::copy_from_slice(key.as_ref());
                    if let Some(last_key) = self.0.last_key.as_ref() {
                        S::ensure_dictionary_key(last_key, &key)?;
                    }
                    self.0.last_key = Some(key);
                }
                key.apply_visit_bytes(visitor)
            }
            token => Err(Error::KeyType {
                type_name: token.to_type_name(),
            }
            .into()),
        }
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
        ignored_any
    }
}
