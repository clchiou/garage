use serde::de::{
    Deserialize, DeserializeOwned, DeserializeSeed, Deserializer, EnumAccess, Error as _, Expected,
    MapAccess, SeqAccess, Unexpected, VariantAccess, Visitor,
};

use crate::bstr::{DeserializableBStr, OwnedBStr};
use crate::de_ext::VisitorExt;
use crate::error::Error;
use crate::raw::MAGIC;

use super::{Dictionary, DictionaryIter, Integer, List, ListIter, Value};

pub fn from_value<T, B>(value: Value<B>) -> Result<T, Error>
where
    T: DeserializeOwned,
    B: OwnedBStr,
{
    T::deserialize(value)
}

pub fn from_borrowed_value<'de, T>(value: Value<&'de [u8]>) -> Result<T, Error>
where
    T: Deserialize<'de>,
{
    T::deserialize(value)
}

impl<B> Value<B>
where
    B: AsRef<[u8]>,
{
    pub(crate) fn to_unexpected(&self) -> Unexpected {
        match self {
            Self::ByteString(bytes) => Unexpected::Bytes(bytes.as_ref()),
            Self::Integer(integer) => Unexpected::Signed(*integer),
            Self::List(_) => Unexpected::Seq,
            Self::Dictionary(_) => Unexpected::Map,
        }
    }
}

impl<'de, B> Value<B>
where
    B: DeserializableBStr<'de>,
{
    fn deserialize_byte_string<V>(self, visitor: &V) -> Result<B, Error>
    where
        V: Visitor<'de>,
    {
        match self {
            Value::ByteString(bytes) => Ok(bytes),
            _ => Err(self.invalid_type(visitor)),
        }
    }

    fn deserialize_integer<V>(self, visitor: &V) -> Result<Integer, Error>
    where
        V: Visitor<'de>,
    {
        match self {
            Value::Integer(integer) => Ok(integer),
            _ => Err(self.invalid_type(visitor)),
        }
    }

    fn deserialize_list<V>(self, visitor: &V) -> Result<List<B>, Error>
    where
        V: Visitor<'de>,
    {
        match self {
            Value::List(list) => Ok(list),
            _ => Err(self.invalid_type(visitor)),
        }
    }

    fn invalid_type(&self, exp: &dyn Expected) -> Error {
        Error::invalid_type(self.to_unexpected(), exp)
    }
}

impl<'de, B> Deserializer<'de> for Value<B>
where
    B: DeserializableBStr<'de>,
{
    type Error = Error;

    fn deserialize_any<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        match self {
            Value::ByteString(bytes) => bytes.apply_visit_bytes(visitor),
            Value::Integer(integer) => visitor.visit_i64(integer),
            Value::List(list) => visitor.visit_seq(ListDeserializer::new(list)),
            Value::Dictionary(dict) => visitor.visit_map(DictionaryDeserializer::new(dict)),
        }
    }

    fn deserialize_bool<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer(&visitor)?;
        visitor.visit_bool_i64(value)
    }

    fn deserialize_f32<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer(&visitor)?;
        visitor.visit_f32(value as f32)
    }

    fn deserialize_f64<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer(&visitor)?;
        visitor.visit_f64(value as f64)
    }

    fn deserialize_char<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_byte_string(&visitor)?;
        visitor.visit_char_bytes(value.as_ref())
    }

    fn deserialize_option<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let mut list = self.deserialize_list(&visitor)?;
        match list.len() {
            0 => visitor.visit_none(),
            1 => visitor.visit_some(list.remove(0)),
            n => Err(Error::invalid_length(n, &visitor)),
        }
    }

    fn deserialize_unit<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        match self.deserialize_list(&visitor)?.len() {
            0 => visitor.visit_unit(),
            n => Err(Error::invalid_length(n, &visitor)),
        }
    }

    fn deserialize_unit_struct<V>(
        self,
        _name: &'static str,
        visitor: V,
    ) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        self.deserialize_unit(visitor)
    }

    fn deserialize_newtype_struct<V>(
        self,
        name: &'static str,
        visitor: V,
    ) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        if name == MAGIC {
            // Not supported for now because it does not appear to be particularly useful.
            Err(Error::custom(
                "deserializing raw bencode from value is not supported for now",
            ))
        } else {
            visitor.visit_newtype_struct(self)
        }
    }

    fn deserialize_tuple<V>(self, len: usize, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let list = self.deserialize_list(&visitor)?;
        if list.len() == len {
            visitor.visit_seq(ListDeserializer::new(list))
        } else {
            Err(Error::invalid_length(list.len(), &visitor))
        }
    }

    fn deserialize_tuple_struct<V>(
        self,
        _name: &'static str,
        len: usize,
        visitor: V,
    ) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        self.deserialize_tuple(len, visitor)
    }

    fn deserialize_struct<V>(
        self,
        _name: &'static str,
        fields: &'static [&'static str],
        visitor: V,
    ) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        match self {
            Value::List(list) => {
                if list.len() == fields.len() {
                    visitor.visit_seq(ListDeserializer::new(list))
                } else {
                    Err(Error::invalid_length(list.len(), &visitor))
                }
            }
            Value::Dictionary(dict) => visitor.visit_map(DictionaryDeserializer::new(dict)),
            _ => Err(self.invalid_type(&visitor)),
        }
    }

    fn deserialize_enum<V>(
        self,
        _name: &'static str,
        _variants: &'static [&'static str],
        visitor: V,
    ) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        match self {
            Value::ByteString(bytes) => visitor.visit_enum(EnumDeserializer::new(bytes, None)),
            Value::Dictionary(mut dict) => match dict.len() {
                1 => {
                    let (variant, value) = dict.pop_first().expect("variant");
                    visitor.visit_enum(EnumDeserializer::new(variant, Some(value)))
                }
                n => Err(Error::invalid_length(n, &visitor)),
            },
            _ => Err(self.invalid_type(&visitor)),
        }
    }

    fn deserialize_identifier<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        self.deserialize_byte_string(&visitor)?
            .apply_visit_bytes(visitor)
    }

    fn deserialize_ignored_any<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        visitor.visit_unit()
    }

    serde::forward_to_deserialize_any! {
        i8 i16 i32 i64 i128
        u8 u16 u32 u64 u128
        str string
        bytes byte_buf
        seq
        map
    }
}

struct ListDeserializer<B>(ListIter<B>);

impl<B> ListDeserializer<B> {
    fn new(list: List<B>) -> Self {
        Self(list.into_iter())
    }
}

impl<'de, B> SeqAccess<'de> for ListDeserializer<B>
where
    B: DeserializableBStr<'de>,
{
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

struct DictionaryDeserializer<B>(DictionaryIter<B>, Option<Value<B>>);

impl<B> DictionaryDeserializer<B> {
    fn new(dict: Dictionary<B>) -> Self {
        Self(dict.into_iter(), None)
    }
}

impl<'de, B> MapAccess<'de> for DictionaryDeserializer<B>
where
    B: DeserializableBStr<'de>,
{
    type Error = Error;

    fn next_key_seed<K>(&mut self, seed: K) -> Result<Option<K::Value>, Self::Error>
    where
        K: DeserializeSeed<'de>,
    {
        self.0
            .next()
            .map(|(key, value)| {
                seed.deserialize(Value::ByteString(key))
                    .inspect(|_| self.1 = Some(value))
            })
            .transpose()
    }

    fn next_value_seed<V>(&mut self, seed: V) -> Result<V::Value, Self::Error>
    where
        V: DeserializeSeed<'de>,
    {
        seed.deserialize(self.1.take().expect("map value"))
    }

    fn next_entry_seed<K, V>(
        &mut self,
        kseed: K,
        vseed: V,
    ) -> Result<Option<(K::Value, V::Value)>, Self::Error>
    where
        K: DeserializeSeed<'de>,
        V: DeserializeSeed<'de>,
    {
        self.0
            .next()
            .map(|(key, value)| {
                Ok((
                    kseed.deserialize(Value::ByteString(key))?,
                    vseed.deserialize(value)?,
                ))
            })
            .transpose()
    }

    fn size_hint(&self) -> Option<usize> {
        Some(self.0.len())
    }
}

struct EnumDeserializer<B>(B, Option<Value<B>>);

struct VariantDeserializer<B>(Option<Value<B>>);

impl<B> EnumDeserializer<B> {
    fn new(variant: B, value: Option<Value<B>>) -> Self {
        Self(variant, value)
    }
}

impl<B> VariantDeserializer<B> {
    fn new(value: Option<Value<B>>) -> Self {
        Self(value)
    }
}

impl<'de, B> EnumAccess<'de> for EnumDeserializer<B>
where
    B: DeserializableBStr<'de>,
{
    type Error = Error;
    type Variant = VariantDeserializer<B>;

    fn variant_seed<V>(self, seed: V) -> Result<(V::Value, Self::Variant), Self::Error>
    where
        V: DeserializeSeed<'de>,
    {
        let Self(variant, value) = self;
        let variant = seed.deserialize(Value::ByteString(variant))?;
        Ok((variant, VariantDeserializer::new(value)))
    }
}

impl<'de, B> VariantAccess<'de> for VariantDeserializer<B>
where
    B: DeserializableBStr<'de>,
{
    type Error = Error;

    fn unit_variant(self) -> Result<(), Self::Error> {
        match self.0 {
            None => Ok(()),
            Some(value) => Err(Error::invalid_type(value.to_unexpected(), &"unit variant")),
        }
    }

    fn newtype_variant_seed<T>(self, seed: T) -> Result<T::Value, Self::Error>
    where
        T: DeserializeSeed<'de>,
    {
        seed.deserialize(self.expect("newtype variant")?)
    }

    fn tuple_variant<V>(self, len: usize, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        self.expect("tuple variant")?
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
        self.expect("struct variant")?
            .deserialize_struct("", fields, visitor)
    }
}

impl<B> VariantDeserializer<B> {
    fn expect(self, exp: &'static str) -> Result<Value<B>, Error> {
        self.0
            .ok_or_else(|| Error::invalid_type(Unexpected::UnitVariant, &exp))
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::collections::HashMap;
    use std::fmt;

    use bytes::Bytes;

    use crate::testing::{
        AdjacentlyTagged, Enum, Flatten, Ignored, InternallyTagged, Newtype, StrictEnum,
        StrictStruct, Struct, Tuple, Unit, Untagged, vb, vd, vi, vl,
    };

    use super::*;

    fn test<'de, T>(value: Value<&'de [u8]>, expect: Result<T, Error>)
    where
        T: Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        assert_eq!(T::deserialize(value), expect);
    }

    fn test_own<T>(value: Value<&[u8]>, expect: Result<T, Error>)
    where
        T: DeserializeOwned,
        T: fmt::Debug + PartialEq,
    {
        assert_eq!(T::deserialize(value.to_own::<Bytes>()), expect);
    }

    fn test_invalid_type<'de, T>(value: Value<&'de [u8]>)
    where
        T: Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        test_err::<T>(value, "invalid type: ")
    }

    fn test_invalid_value<'de, T>(value: Value<&'de [u8]>)
    where
        T: Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        test_err::<T>(value, "invalid value: ")
    }

    fn test_invalid_length<'de, T>(value: Value<&'de [u8]>)
    where
        T: Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        test_err::<T>(value, "invalid length ")
    }

    fn test_missing_field<'de, T>(value: Value<&'de [u8]>)
    where
        T: Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        test_err::<T>(value, "missing field ")
    }

    fn test_unknown_field<'de, T>(value: Value<&'de [u8]>)
    where
        T: Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        test_err::<T>(value, "unknown field ")
    }

    fn test_err<'de, T>(value: Value<&'de [u8]>, prefix: &str)
    where
        T: Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        assert_matches!(
            T::deserialize(value),
            Err(error) if error.to_string().starts_with(prefix),
            "prefix = {prefix:?}",
        );
    }

    #[test]
    fn deserialize_bool() {
        test(Value::Integer(1), Ok(true));
        test(Value::Integer(0), Ok(false));
        test_invalid_type::<bool>(Value::ByteString(b""));
        test_invalid_value::<bool>(Value::Integer(2));
    }

    #[test]
    fn deserialize_int() {
        test(Value::Integer(-1), Ok(-1i8));
        test(Value::Integer(-1), Ok(-1i16));
        test(Value::Integer(-1), Ok(-1i32));
        test(Value::Integer(-1), Ok(-1i64));
        test(Value::Integer(-1), Ok(-1i128));

        test(Value::Integer(42), Ok(42u8));
        test(Value::Integer(42), Ok(42u16));
        test(Value::Integer(42), Ok(42u32));
        test(Value::Integer(42), Ok(42u64));
        test(Value::Integer(42), Ok(42u128));

        test_invalid_type::<i8>(Value::ByteString(b""));
        test_invalid_type::<i16>(Value::ByteString(b""));
        test_invalid_type::<i32>(Value::ByteString(b""));
        test_invalid_type::<i64>(Value::ByteString(b""));
        test_invalid_type::<i128>(Value::ByteString(b""));

        test_invalid_type::<u8>(Value::ByteString(b""));
        test_invalid_type::<u16>(Value::ByteString(b""));
        test_invalid_type::<u32>(Value::ByteString(b""));
        test_invalid_type::<u64>(Value::ByteString(b""));
        test_invalid_type::<u128>(Value::ByteString(b""));

        test_invalid_value::<i8>(Value::Integer(i64::MAX));
        test_invalid_value::<i16>(Value::Integer(i64::MAX));
        test_invalid_value::<i32>(Value::Integer(i64::MAX));

        test_invalid_value::<u8>(Value::Integer(-1));
        test_invalid_value::<u16>(Value::Integer(-1));
        test_invalid_value::<u32>(Value::Integer(-1));
        test_invalid_value::<u64>(Value::Integer(-1));
        test_invalid_value::<u128>(Value::Integer(-1));
    }

    #[test]
    fn deserialize_float() {
        test(Value::Integer(1), Ok(1.0f32));
        test(Value::Integer(2), Ok(2.0f64));
    }

    #[test]
    fn deserialize_char() {
        test(Value::ByteString(b"A"), Ok('A'));
        test(Value::ByteString(b"\xe2\x9d\xa4"), Ok('\u{2764}'));
        test_invalid_type::<char>(Value::Integer(0));
        test_invalid_value::<char>(Value::ByteString(b""));
        test_invalid_value::<char>(Value::ByteString(b"\x80"));
        test_invalid_value::<char>(Value::ByteString(b"AB"));
    }

    #[test]
    fn deserialize_str() {
        fn test_str(expect: &str) {
            let testdata = expect.as_bytes();
            test(Value::ByteString(testdata), Ok(expect));
            test_own(Value::ByteString(testdata), Ok(expect.to_string()));
        }

        test_str("");
        test_str("hello world");
        test_str("\u{2764}");
        test_str("\x00");

        test_invalid_type::<&str>(Value::Integer(0));
        test_invalid_value::<&str>(Value::ByteString(b"\x80"));
    }

    #[test]
    fn deserialize_bytes() {
        fn test_bytes(expect: &[u8]) {
            test(Value::ByteString(expect), Ok(expect));
            test_own(
                Value::ByteString(expect),
                Ok(Bytes::copy_from_slice(expect)),
            );
        }

        test_bytes(b"");
        test_bytes(b"hello world");
        test_bytes(b"\xe2\x9d\xa4");
        test_bytes(b"\x00");

        test_invalid_type::<&[u8]>(Value::Integer(0));
    }

    #[test]
    fn deserialize_option() {
        test(vl([vi(1)]), Ok(Some(1u8)));
        test(vl([]), Ok(None::<u8>));
        test_invalid_type::<Option<u8>>(Value::Integer(0));
        test_invalid_length::<Option<u8>>(vl([vi(0), vi(1)]));
    }

    #[test]
    fn deserialize_unit() {
        test(vl([]), Ok(()));
        test_invalid_type::<()>(Value::Integer(0));
        test_invalid_length::<()>(vl([vi(0)]));
    }

    #[test]
    fn deserialize_unit_struct() {
        test(vl([]), Ok(Unit));
        test_invalid_type::<Unit>(Value::Integer(0));
        test_invalid_length::<Unit>(vl([vi(0)]));
    }

    #[test]
    fn deserialize_newtype_struct() {
        test(
            Value::ByteString(b"\xe2\x9d\xa4"),
            Ok(Newtype("\u{2764}".to_string())),
        );
        test_invalid_type::<Newtype>(Value::Integer(0));
        test_invalid_value::<Newtype>(Value::ByteString(b"\x80"));
    }

    #[test]
    fn deserialize_seq() {
        test(vl([]), Ok(Vec::<u8>::new()));
        test(vl([vi(42)]), Ok(vec![42u8]));
        test_invalid_type::<Vec<u8>>(vd([]));
    }

    #[test]
    fn deserialize_tuple() {
        test(vl([vi(1), vb(b"x")]), Ok((1u8, "x")));
        test_invalid_length::<(u8, u8)>(vl([vi(1)]));
        test_invalid_length::<(u8,)>(vl([vi(1), vi(2)]));

        test_invalid_type::<(u8,)>(vd([]));
        test_invalid_type::<(u8, &str)>(vl([vb(b"x"), vi(1)]));
    }

    #[test]
    fn deserialize_tuple_struct() {
        test(vl([vi(1), vb(b"x")]), Ok(Tuple(1, "x".to_string())));
        test_invalid_length::<Tuple>(vl([vi(1)]));
        test_invalid_length::<Tuple>(vl([vi(1), vb(b"x"), vi(2)]));

        test_invalid_type::<Tuple>(vd([]));
        test_invalid_type::<Tuple>(vl([vb(b"x"), vi(1)]));
    }

    #[test]
    fn deserialize_map() {
        test(vd([]), Ok(HashMap::<&str, u8>::from([])));
        test(vd([(b"k1", vi(1))]), Ok(HashMap::from([("k1", 1u8)])));
        test(
            vd([(b"k1", vi(1)), (b"k2", vi(2))]),
            Ok(HashMap::from([("k1", 1u8), ("k2", 2u8)])),
        );

        test_invalid_type::<HashMap<&str, u8>>(Value::Integer(0));
    }

    #[test]
    fn deserialize_struct() {
        let dict = vd([(b"a", vi(1)), (b"c", vi(2)), (b"b", vi(3)), (b"x", vi(4))]);
        test(dict.clone(), Ok(Struct { a: 1, c: 2, b: 3 }));
        test_missing_field::<Struct>(vd([]));
        test_unknown_field::<StrictStruct>(dict);

        test(vl([vi(1), vi(2), vi(3)]), Ok(Struct { a: 1, c: 2, b: 3 }));
        test_invalid_length::<Struct>(vl([vi(0), vi(0)]));
        test_invalid_length::<Struct>(vl([vi(0), vi(0), vi(0), vi(0)]));

        test_invalid_type::<Struct>(Value::Integer(0));
    }

    #[test]
    fn deserialize_enum() {
        test_invalid_type::<Enum>(Value::Integer(0));
        test_invalid_length::<Enum>(vd([
            (b"Newtype", vb(b"")),
            (b"Tuple", vl([vi(0), vb(b"")])),
        ]));
        test_err::<Enum>(vb(b"X"), "unknown variant ");
        test_err::<Enum>(vd([(b"X", vi(0))]), "unknown variant ");
    }

    #[test]
    fn deserialize_enum_unit() {
        test(vb(b"Unit"), Ok(Enum::Unit));
        test_invalid_type::<Enum>(vd([(b"Unit", vl([]))]));
    }

    #[test]
    fn deserialize_enum_newtype() {
        test(
            vd([(b"Newtype", vb(b"spam egg"))]),
            Ok(Enum::Newtype("spam egg".to_string())),
        );
        test_invalid_type::<Enum>(vb(b"Newtype"));
    }

    #[test]
    fn deserialize_enum_tuple() {
        test(
            vd([(b"Tuple", vl([vi(42), vb(b"spam egg")]))]),
            Ok(Enum::Tuple(42, "spam egg".to_string())),
        );
        test_invalid_length::<Enum>(vd([(b"Tuple", vl([vi(0)]))]));
        test_invalid_length::<Enum>(vd([(b"Tuple", vl([vi(0), vb(b""), vi(0)]))]));

        test_invalid_type::<Enum>(vb(b"Tuple"));
        test_invalid_type::<Enum>(vd([(b"Tuple", vd([]))]));
    }

    #[test]
    fn deserialize_enum_struct() {
        test(
            vd([(
                b"Struct",
                vd([(b"a", vi(1)), (b"c", vi(2)), (b"b", vi(3)), (b"x", vi(4))]),
            )]),
            Ok(Enum::Struct { a: 1, c: 2, b: 3 }),
        );
        test_missing_field::<Enum>(vd([(b"Struct", vd([]))]));
        test_unknown_field::<StrictEnum>(vd([(b"Struct", vd([(b"x", vi(42)), (b"y", vi(0))]))]));

        test(
            vd([(b"Struct", vl([vi(1), vi(2), vi(3)]))]),
            Ok(Enum::Struct { a: 1, c: 2, b: 3 }),
        );
        test_invalid_length::<Enum>(vd([(b"Struct", vl([vi(0), vi(0)]))]));
        test_invalid_length::<Enum>(vd([(b"Struct", vl([vi(0), vi(0), vi(0), vi(0)]))]));

        test_invalid_type::<Enum>(vb(b"Struct"));
        test_invalid_type::<Enum>(vd([(b"Struct", vi(42))]));
    }

    #[test]
    fn deserialize_identifier() {
        test(vb(b"Unit"), Ok(Enum::Unit));
        test_own(vb(b"Unit"), Ok(Enum::Unit));
    }

    #[test]
    fn deserialize_ignored_any() {
        test(
            vd([(b"x", vi(42)), (b"ignored", vb(b"ignored value"))]),
            Ok(Ignored { x: 42, ignored: 0 }),
        );
    }

    #[test]
    fn nested() {
        test(vl([vl([vl([vi(0)])])]), Ok(vec![vec![vec![0u8]]]));

        test(
            vd([(b"a", vd([(b"b", vd([(b"c", vb(b"d"))]))]))]),
            Ok(HashMap::from([(
                "a",
                HashMap::from([("b", HashMap::from([("c", "d")]))]),
            )])),
        );

        test(
            vd([(b"a", vl([vd([(b"b", vl([vd([(b"c", vb(b"d"))])]))])]))]),
            Ok(HashMap::from([(
                "a",
                vec![HashMap::from([("b", vec![HashMap::from([("c", "d")])])])],
            )])),
        );
    }

    //
    // TODO: It is unfortunate that we cannot support deserialization for non-default enum
    // representations.  Bencode, being a rather limited data format, requires that a caller
    // provide hints to the deserializer to correctly deserialize Serde data types such as `bool`
    // and `char`.  However, the way Serde implements deserialization for non-default enum
    // representations breaks this tight coupling.
    //
    #[test]
    fn enum_repr() {
        test_err::<InternallyTagged>(
            vd([(b"t", vb(b"Bool")), (b"value", vi(1))]),
            "invalid type: integer `1`, expected a boolean",
        );
        test_err::<InternallyTagged>(
            vd([(b"t", vb(b"Char")), (b"value", vb(b"c"))]),
            "invalid type: byte array, expected a char",
        );

        test_err::<AdjacentlyTagged>(
            vd([(b"t", vb(b"Bool")), (b"c", vd([(b"value", vi(1))]))]),
            "invalid type: integer `1`, expected a boolean",
        );
        test_err::<AdjacentlyTagged>(
            vd([(b"t", vb(b"Char")), (b"c", vd([(b"value", vb(b"c"))]))]),
            "invalid type: byte array, expected a char",
        );

        test_err::<Untagged>(
            vd([(b"value", vi(1))]),
            "data did not match any variant of untagged enum Untagged",
        );
        test_err::<Untagged>(
            vd([(b"value", vb(b"c"))]),
            "data did not match any variant of untagged enum Untagged",
        );
    }

    #[test]
    fn flatten() {
        test_own(
            vd([
                (b"a", vi(1)),
                (b"c", vi(2)),
                (b"b", vi(3)),
                (b"x", vi(4)),
                (b"y", vb(b"spam egg")),
            ]),
            Ok(Flatten {
                a: 1,
                c: 2,
                b: 3,
                rest: vd([(b"x", vi(4)), (b"y", vb(b"spam egg"))]).to_own(),
            }),
        );

        // `serde(flatten)` does not support deserialization from a sequence.
        test_invalid_type::<Flatten>(vl([]));
    }
}
