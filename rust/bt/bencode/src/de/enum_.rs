use serde::de::{
    DeserializeSeed, Deserializer as _, EnumAccess, Unexpected, VariantAccess, Visitor,
};

use crate::error;

use super::Deserializer;
use super::dict::DictionaryDeserializer;
use super::read::ReadExt;
use super::strict::Strictness;

//
// `EnumDeserializer`
//

pub(super) struct EnumDeserializer<'b, 'a, R, E, S>(&'b mut DictionaryDeserializer<'a, R, E, S>);

impl<'b, 'a, R, E, S> EnumDeserializer<'b, 'a, R, E, S> {
    pub(super) fn new(deserializer: &'b mut DictionaryDeserializer<'a, R, E, S>) -> Self {
        Self(deserializer)
    }
}

impl<'de, 'b, 'a, R, E, S> EnumAccess<'de> for EnumDeserializer<'b, 'a, R, E, S>
where
    R: ReadExt<'de, S, E>,
    E: error::de::Error,
    S: Strictness,
{
    type Error = E;
    type Variant = Self;

    fn variant_seed<V>(self, seed: V) -> Result<(V::Value, Self::Variant), Self::Error>
    where
        V: DeserializeSeed<'de>,
    {
        let variant = seed.deserialize(&mut self.0.deserialize_key()?.expect("enum variant"))?;
        Ok((variant, self))
    }
}

impl<'de, 'b, 'a, R, E, S> VariantAccess<'de> for EnumDeserializer<'b, 'a, R, E, S>
where
    R: ReadExt<'de, S, E>,
    E: error::de::Error,
    S: Strictness,
{
    type Error = E;

    fn unit_variant(self) -> Result<(), Self::Error> {
        Err(E::invalid_type(
            self.0
                .deserialize_value()?
                .deserialize_token()?
                .to_unexpected(),
            &"unit variant",
        ))
    }

    fn newtype_variant_seed<T>(self, seed: T) -> Result<T::Value, Self::Error>
    where
        T: DeserializeSeed<'de>,
    {
        seed.deserialize(self.0.deserialize_value()?)
    }

    fn tuple_variant<V>(self, len: usize, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        self.0
            .deserialize_value()?
            .deserialize_tuple_struct("", len, visitor)
    }

    fn struct_variant<V>(
        self,
        fields: &'static [&'static str],
        visitor: V,
    ) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        self.0
            .deserialize_value()?
            .deserialize_struct("", fields, visitor)
    }
}

//
// `UnitVariantDeserializer`
//

pub(super) struct UnitVariantDeserializer<'a, R, E, S>(&'a mut Deserializer<R, E, S>);

impl<'a, R, E, S> UnitVariantDeserializer<'a, R, E, S> {
    pub(super) fn new(deserializer: &'a mut Deserializer<R, E, S>) -> Self {
        Self(deserializer)
    }
}

impl<'de, 'a, R, E, S> EnumAccess<'de> for UnitVariantDeserializer<'a, R, E, S>
where
    R: ReadExt<'de, S, E>,
    E: error::de::Error,
    S: Strictness,
{
    type Error = E;
    type Variant = Self;

    fn variant_seed<V>(self, seed: V) -> Result<(V::Value, Self::Variant), Self::Error>
    where
        V: DeserializeSeed<'de>,
    {
        let variant = seed.deserialize(&mut *self.0)?;
        Ok((variant, self))
    }
}

impl<'de, 'a, R, E, S> VariantAccess<'de> for UnitVariantDeserializer<'a, R, E, S>
where
    E: error::de::Error,
{
    type Error = E;

    fn unit_variant(self) -> Result<(), Self::Error> {
        Ok(())
    }

    fn newtype_variant_seed<T>(self, _seed: T) -> Result<T::Value, Self::Error>
    where
        T: DeserializeSeed<'de>,
    {
        Err(E::invalid_type(Unexpected::UnitVariant, &"newtype variant"))
    }

    fn tuple_variant<V>(self, _len: usize, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        Err(E::invalid_type(Unexpected::UnitVariant, &visitor))
    }

    fn struct_variant<V>(
        self,
        _fields: &'static [&'static str],
        visitor: V,
    ) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        Err(E::invalid_type(Unexpected::UnitVariant, &visitor))
    }
}
