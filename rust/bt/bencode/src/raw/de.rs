use std::marker::PhantomData;

use serde::de::{self, DeserializeSeed, SeqAccess, Visitor};

use crate::bstr::DeserializableBStr;
use crate::de::Deserializer;
use crate::de::read::{Read, Tee};
use crate::de::strict::Strictness;
use crate::error;

pub(crate) struct RawTupleDeserializer<R, D, E, S>(Option<RawTuple<R, D, E, S>>);

enum RawTuple<R, D, E, S> {
    RawValue(Deserializer<R, E, S>),
    RawData(D),
}

impl<R, D, E, S> RawTupleDeserializer<R, D, E, S> {
    pub(crate) fn new(deserializer: Deserializer<R, E, S>) -> Self {
        Self(Some(RawTuple::RawValue(deserializer)))
    }
}

impl<'de, R, D, E, S> SeqAccess<'de> for RawTupleDeserializer<R, D, E, S>
where
    R: Read<'de, E> + Tee<'de, Bytes = D>,
    D: DeserializableBStr<'de>,
    E: error::de::Error,
    S: Strictness,
{
    type Error = E;

    fn next_element_seed<T>(&mut self, seed: T) -> Result<Option<T::Value>, Self::Error>
    where
        T: DeserializeSeed<'de>,
    {
        self.0
            .take()
            .map(|state| match state {
                RawTuple::RawValue(mut deserializer) => seed
                    .deserialize(&mut deserializer)
                    .inspect(|_| self.0 = Some(RawTuple::RawData(deserializer.into_bytes()))),
                RawTuple::RawData(data) => seed.deserialize(RawDataDeserializer::new(data)),
            })
            .transpose()
    }

    fn size_hint(&self) -> Option<usize> {
        Some(2)
    }
}

struct RawDataDeserializer<D, E>(D, PhantomData<E>);

impl<D, E> RawDataDeserializer<D, E> {
    fn new(data: D) -> Self {
        Self(data, PhantomData)
    }
}

impl<'de, D, E> de::Deserializer<'de> for RawDataDeserializer<D, E>
where
    D: DeserializableBStr<'de>,
    E: error::de::Error,
{
    type Error = E;

    fn deserialize_any<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        self.0.apply_visit_bytes(visitor)
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
