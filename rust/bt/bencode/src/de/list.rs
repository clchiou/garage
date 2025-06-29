use std::fmt;

use serde::de::{DeserializeSeed, SeqAccess};

use crate::error;

use super::Deserializer;
use super::read::ReadExt;
use super::strict::Strictness;

pub(super) struct ListDeserializer<'a, R, E, S>(&'a mut Deserializer<R, E, S>);

impl<'a, R, E, S> ListDeserializer<'a, R, E, S> {
    pub(super) fn new(deserializer: &'a mut Deserializer<R, E, S>) -> Self {
        Self(deserializer)
    }
}

impl<'de, 'a, R, E, S> ListDeserializer<'a, R, E, S>
where
    R: ReadExt<'de, S, E>,
    E: error::de::Error,
    S: Strictness,
{
    pub(super) fn deserialize_item(&mut self) -> Result<Option<&mut Deserializer<R, E, S>>, E> {
        Ok(self.0.deserialize_item_token()?.map(|token| {
            self.0.undeserialize_token(token);
            &mut *self.0
        }))
    }

    // When the visitor is not expected to consume the entire list (e.g., a tuple visitor), our
    // `Deserializer` should invoke this after `visit_seq` returns.
    pub(super) fn deserialize_end(&mut self, expect_len: usize) -> Result<(), E> {
        match self.0.deserialize_item_token()? {
            None => Ok(()),
            Some(_) => Err(E::custom(fmt::from_fn(|f| {
                std::write!(f, "invalid length of list, expected {expect_len}")
            }))),
        }
    }
}

impl<'de, 'a, R, E, S> SeqAccess<'de> for &mut ListDeserializer<'a, R, E, S>
where
    R: ReadExt<'de, S, E>,
    E: error::de::Error,
    S: Strictness,
{
    type Error = E;

    fn next_element_seed<T>(&mut self, seed: T) -> Result<Option<T::Value>, Self::Error>
    where
        T: DeserializeSeed<'de>,
    {
        self.deserialize_item()?
            .map(|deserializer| seed.deserialize(deserializer))
            .transpose()
    }
}
