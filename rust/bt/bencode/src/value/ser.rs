use std::fmt;
use std::marker::PhantomData;

use serde::ser::{
    self, Error as _, Serialize, SerializeMap, SerializeSeq, SerializeStruct,
    SerializeStructVariant, SerializeTuple, SerializeTupleStruct, SerializeTupleVariant,
};

use crate::bstr::OwnedBStr;
use crate::error::Error;
use crate::raw::MAGIC;
use crate::raw::ser::RawValueSerializer;

use super::int::FromInt;
use super::{Dictionary, Integer, List, Value};

pub fn to_value<T, B>(value: &T) -> Result<Value<B>, Error>
where
    T: ?Sized + ser::Serialize,
    B: OwnedBStr,
{
    value.serialize(Serializer::new())
}

pub(crate) fn serialize_key<K, B>(key: &K) -> Result<B, Error>
where
    K: ?Sized + Serialize,
    B: OwnedBStr,
{
    match key.serialize(Serializer::new())? {
        Value::ByteString(bytes) => Ok(bytes),
        key => Err(Error::custom(fmt::from_fn(move |f| {
            std::write!(f, "expect byte string dictionary key: {key:?}")
        }))),
    }
}

pub struct Serializer<B>(PhantomData<B>);

pub struct ListSerializer<B, T>(List<B>, T);

pub struct DictionarySerializer<B, T>(Dictionary<B>, T);

impl<B> Default for Serializer<B> {
    fn default() -> Self {
        Self::new()
    }
}

impl<B> Serializer<B> {
    pub fn new() -> Self {
        Self(PhantomData)
    }
}

impl<B> ListSerializer<B, ()> {
    fn new(len: usize) -> Self {
        Self(List::with_capacity(len), ())
    }
}

impl<B> ListSerializer<B, &'static str> {
    fn new_tuple_variant(name: &'static str, len: usize) -> Self {
        Self(List::with_capacity(len), name)
    }
}

impl<B> DictionarySerializer<B, Option<B>> {
    fn new_map() -> Self {
        Self(Dictionary::new(), None)
    }
}

impl<B> DictionarySerializer<B, ()> {
    fn new_struct() -> Self {
        Self(Dictionary::new(), ())
    }
}

impl<B> DictionarySerializer<B, &'static str> {
    fn new_struct_variant(name: &'static str) -> Self {
        Self(Dictionary::new(), name)
    }
}

impl<B> ser::Serializer for Serializer<B>
where
    B: OwnedBStr,
{
    type Ok = Value<B>;
    type Error = Error;

    type SerializeSeq = ListSerializer<B, ()>;
    type SerializeTuple = ListSerializer<B, ()>;
    type SerializeTupleStruct = ListSerializer<B, ()>;
    type SerializeTupleVariant = ListSerializer<B, &'static str>;

    type SerializeMap = DictionarySerializer<B, Option<B>>;
    type SerializeStruct = DictionarySerializer<B, ()>;
    type SerializeStructVariant = DictionarySerializer<B, &'static str>;

    fn serialize_bool(self, value: bool) -> Result<Self::Ok, Self::Error> {
        self.serialize_i64(value.into())
    }

    fn serialize_i8(self, value: i8) -> Result<Self::Ok, Self::Error> {
        self.serialize_i64(value.into())
    }

    fn serialize_i16(self, value: i16) -> Result<Self::Ok, Self::Error> {
        self.serialize_i64(value.into())
    }

    fn serialize_i32(self, value: i32) -> Result<Self::Ok, Self::Error> {
        self.serialize_i64(value.into())
    }

    fn serialize_i64(self, value: i64) -> Result<Self::Ok, Self::Error> {
        Ok(Value::Integer(value))
    }

    fn serialize_i128(self, value: i128) -> Result<Self::Ok, Self::Error> {
        self.serialize_i64(Integer::ser_from_int(value)?)
    }

    fn serialize_u8(self, value: u8) -> Result<Self::Ok, Self::Error> {
        self.serialize_u64(value.into())
    }

    fn serialize_u16(self, value: u16) -> Result<Self::Ok, Self::Error> {
        self.serialize_u64(value.into())
    }

    fn serialize_u32(self, value: u32) -> Result<Self::Ok, Self::Error> {
        self.serialize_u64(value.into())
    }

    fn serialize_u64(self, value: u64) -> Result<Self::Ok, Self::Error> {
        self.serialize_i64(Integer::ser_from_int(value)?)
    }

    fn serialize_u128(self, value: u128) -> Result<Self::Ok, Self::Error> {
        self.serialize_i64(Integer::ser_from_int(value)?)
    }

    fn serialize_f32(self, value: f32) -> Result<Self::Ok, Self::Error> {
        self.serialize_i64(value as Integer)
    }

    fn serialize_f64(self, value: f64) -> Result<Self::Ok, Self::Error> {
        self.serialize_i64(value as Integer)
    }

    fn serialize_char(self, value: char) -> Result<Self::Ok, Self::Error> {
        self.serialize_str(value.encode_utf8(&mut [0u8; 4]))
    }

    fn serialize_str(self, value: &str) -> Result<Self::Ok, Self::Error> {
        self.serialize_bytes(value.as_bytes())
    }

    fn serialize_bytes(self, value: &[u8]) -> Result<Self::Ok, Self::Error> {
        Ok(Value::ByteString(B::from_bytes(value)))
    }

    fn serialize_none(self) -> Result<Self::Ok, Self::Error> {
        Ok(Value::List([].into()))
    }

    fn serialize_some<T>(self, value: &T) -> Result<Self::Ok, Self::Error>
    where
        T: ?Sized + Serialize,
    {
        Ok(Value::List([value.serialize(self)?].into()))
    }

    fn serialize_unit(self) -> Result<Self::Ok, Self::Error> {
        Ok(Value::List([].into()))
    }

    fn serialize_unit_struct(self, _name: &'static str) -> Result<Self::Ok, Self::Error> {
        Ok(Value::List([].into()))
    }

    fn serialize_unit_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
    ) -> Result<Self::Ok, Self::Error> {
        self.serialize_str(variant)
    }

    fn serialize_newtype_struct<T>(
        self,
        name: &'static str,
        value: &T,
    ) -> Result<Self::Ok, Self::Error>
    where
        T: ?Sized + Serialize,
    {
        if name == MAGIC {
            value.serialize(RawValueSerializer::new())
        } else {
            value.serialize(self)
        }
    }

    fn serialize_newtype_variant<T>(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
        value: &T,
    ) -> Result<Self::Ok, Self::Error>
    where
        T: ?Sized + Serialize,
    {
        serialize_variant(variant, value.serialize(self)?)
    }

    fn serialize_seq(self, len: Option<usize>) -> Result<Self::SerializeSeq, Self::Error> {
        Ok(ListSerializer::new(len.unwrap_or(0)))
    }

    fn serialize_tuple(self, len: usize) -> Result<Self::SerializeTuple, Self::Error> {
        Ok(ListSerializer::new(len))
    }

    fn serialize_tuple_struct(
        self,
        _name: &'static str,
        len: usize,
    ) -> Result<Self::SerializeTupleStruct, Self::Error> {
        Ok(ListSerializer::new(len))
    }

    fn serialize_tuple_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
        len: usize,
    ) -> Result<Self::SerializeTupleVariant, Self::Error> {
        Ok(ListSerializer::new_tuple_variant(variant, len))
    }

    fn serialize_map(self, _len: Option<usize>) -> Result<Self::SerializeMap, Self::Error> {
        Ok(DictionarySerializer::new_map())
    }

    fn serialize_struct(
        self,
        _name: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeStruct, Self::Error> {
        Ok(DictionarySerializer::new_struct())
    }

    fn serialize_struct_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeStructVariant, Self::Error> {
        Ok(DictionarySerializer::new_struct_variant(variant))
    }
}

impl<B> SerializeSeq for ListSerializer<B, ()>
where
    B: OwnedBStr,
{
    type Ok = Value<B>;
    type Error = Error;

    fn serialize_element<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        self.0.push(value.serialize(Serializer::new())?);
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        let Self(list, ()) = self;
        Ok(Value::List(list))
    }
}

impl<B> SerializeTuple for ListSerializer<B, ()>
where
    B: OwnedBStr,
{
    type Ok = Value<B>;
    type Error = Error;

    fn serialize_element<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        self.0.push(value.serialize(Serializer::new())?);
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        let Self(list, ()) = self;
        Ok(Value::List(list))
    }
}

impl<B> SerializeTupleStruct for ListSerializer<B, ()>
where
    B: OwnedBStr,
{
    type Ok = Value<B>;
    type Error = Error;

    fn serialize_field<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        self.0.push(value.serialize(Serializer::new())?);
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        let Self(list, ()) = self;
        Ok(Value::List(list))
    }
}

impl<B> SerializeTupleVariant for ListSerializer<B, &'static str>
where
    B: OwnedBStr,
{
    type Ok = Value<B>;
    type Error = Error;

    fn serialize_field<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        self.0.push(value.serialize(Serializer::new())?);
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        let Self(list, name) = self;
        serialize_variant(name, Value::List(list))
    }
}

impl<B> SerializeMap for DictionarySerializer<B, Option<B>>
where
    B: OwnedBStr,
{
    type Ok = Value<B>;
    type Error = Error;

    fn serialize_key<T>(&mut self, key: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        self.1 = Some(serialize_key(key)?);
        Ok(())
    }

    fn serialize_value<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        let key = self.1.take().expect("map key");
        self.0.insert(key, value.serialize(Serializer::new())?);
        Ok(())
    }

    fn serialize_entry<K, V>(&mut self, key: &K, value: &V) -> Result<(), Self::Error>
    where
        K: ?Sized + Serialize,
        V: ?Sized + Serialize,
    {
        self.0
            .insert(serialize_key(key)?, value.serialize(Serializer::new())?);
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        let Self(dict, _) = self;
        Ok(Value::Dictionary(dict))
    }
}

impl<B> SerializeStruct for DictionarySerializer<B, ()>
where
    B: OwnedBStr,
{
    type Ok = Value<B>;
    type Error = Error;

    fn serialize_field<T>(&mut self, key: &'static str, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        self.0
            .insert(from_static(key), value.serialize(Serializer::new())?);
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        let Self(dict, ()) = self;
        Ok(Value::Dictionary(dict))
    }
}

impl<B> SerializeStructVariant for DictionarySerializer<B, &'static str>
where
    B: OwnedBStr,
{
    type Ok = Value<B>;
    type Error = Error;

    fn serialize_field<T>(&mut self, key: &'static str, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        self.0
            .insert(from_static(key), value.serialize(Serializer::new())?);
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        let Self(dict, name) = self;
        serialize_variant(name, Value::Dictionary(dict))
    }
}

fn serialize_variant<B>(variant: &'static str, value: Value<B>) -> Result<Value<B>, Error>
where
    B: OwnedBStr,
{
    Ok(Value::Dictionary([(from_static(variant), value)].into()))
}

fn from_static<B>(key: &'static str) -> B
where
    B: OwnedBStr,
{
    B::from_static_bytes(key.as_bytes())
}

#[cfg(test)]
mod tests {
    use std::any;
    use std::assert_matches::assert_matches;
    use std::collections::HashMap;

    use bytes::Bytes;

    use crate::int::Int;
    use crate::testing::{Enum, Flatten, Ignored, Newtype, Struct, Tuple, Unit, vb, vd, vi, vl};

    use super::*;

    fn test<T>(testdata: T, expect: Result<Value<&[u8]>, Error>)
    where
        T: Serialize,
    {
        assert_eq!(
            testdata.serialize(Serializer::new()),
            expect.map(|value| value.to_own::<Bytes>()),
        );
    }

    #[test]
    fn serialize_bool() {
        test(true, Ok(vi(1)));
        test(false, Ok(vi(0)));
    }

    #[test]
    fn serialize_int() {
        fn test_err<I>(value: I)
        where
            I: Int + Serialize,
        {
            test(
                value,
                Err(Error::custom(std::format!(
                    "{}-to-i64 overflow: {}",
                    any::type_name::<I>(),
                    value,
                ))),
            );
        }

        test(i8::MIN, Ok(vi(i8::MIN.into())));
        test(i8::MAX, Ok(vi(i8::MAX.into())));
        test(i16::MIN, Ok(vi(i16::MIN.into())));
        test(i16::MAX, Ok(vi(i16::MAX.into())));
        test(i32::MIN, Ok(vi(i32::MIN.into())));
        test(i32::MAX, Ok(vi(i32::MAX.into())));
        test(i64::MIN, Ok(vi(i64::MIN.into())));
        test(i64::MAX, Ok(vi(i64::MAX.into())));
        test_err(i128::from(i64::MIN) - 1);
        test_err(i128::from(i64::MAX) + 1);

        test(u8::MAX, Ok(vi(u8::MAX.into())));
        test(u16::MAX, Ok(vi(u16::MAX.into())));
        test(u32::MAX, Ok(vi(u32::MAX.into())));
        test_err(u64::try_from(i64::MAX).unwrap() + 1);
        test_err(u128::try_from(i64::MAX).unwrap() + 1);
    }

    #[test]
    fn serialize_float() {
        test(1.5f32, Ok(vi(1)));
        test(2.5f64, Ok(vi(2)));
    }

    #[test]
    fn serialize_char() {
        test('A', Ok(vb(b"A")));
        test('\u{2764}', Ok(vb(b"\xe2\x9d\xa4")));
    }

    #[test]
    fn serialize_str() {
        test("", Ok(vb(b"")));
        test("hello world", Ok(vb(b"hello world")));
        test("\u{2764}", Ok(vb(b"\xe2\x9d\xa4")));
        test("\x00", Ok(vb(b"\x00")));
    }

    #[test]
    fn serialize_bytes() {
        use serde_bytes::Bytes;

        test(Bytes::new(b""), Ok(vb(b"")));
        test(Bytes::new(b"hello world"), Ok(vb(b"hello world")));
        test(Bytes::new(b"\xe2\x9d\xa4"), Ok(vb(b"\xe2\x9d\xa4")));
        test(Bytes::new(b"\x00"), Ok(vb(b"\x00")));
    }

    #[test]
    fn serialize_option() {
        test(Some(42u8), Ok(vl([vi(42)])));
        test(None::<u8>, Ok(vl([])));
    }

    #[test]
    fn serialize_unit() {
        test((), Ok(vl([])));
    }

    #[test]
    fn serialize_unit_struct() {
        test(Unit, Ok(vl([])));
    }

    #[test]
    fn serialize_unit_variant() {
        test(Enum::Unit, Ok(vb(b"Unit")));
    }

    #[test]
    fn serialize_newtype_struct() {
        test(Newtype("hello world".to_string()), Ok(vb(b"hello world")));
    }

    #[test]
    fn serialize_newtype_variant() {
        test(
            Enum::Newtype("hello world".to_string()),
            Ok(vd([(b"Newtype", vb(b"hello world"))])),
        );
    }

    #[test]
    fn serialize_seq() {
        test(Vec::<u8>::new(), Ok(vl([])));
        test(vec![1u8], Ok(vl([vi(1)])));
        test(vec![1u8, 2u8], Ok(vl([vi(1), vi(2)])));
    }

    #[test]
    fn serialize_tuple() {
        test((1u8,), Ok(vl([vi(1)])));
        test((1u8, "spam egg"), Ok(vl([vi(1), vb(b"spam egg")])));
    }

    #[test]
    fn serialize_tuple_struct() {
        test(
            Tuple(1u8, "spam egg".to_string()),
            Ok(vl([vi(1), vb(b"spam egg")])),
        );
    }

    #[test]
    fn serialize_tuple_variant() {
        test(
            Enum::Tuple(1u8, "spam egg".to_string()),
            Ok(vd([(b"Tuple", vl([vi(1), vb(b"spam egg")]))])),
        );
    }

    #[test]
    fn serialize_map() {
        test(HashMap::<&str, u8>::from([]), Ok(vd([])));
        test(
            HashMap::from([("k1", 1u8), ("k2", 2u8)]),
            Ok(vd([(b"k1", vi(1)), (b"k2", vi(2))])),
        );

        test(
            HashMap::from([(0u8, 0u8)]),
            Err(Error::custom(
                "expect byte string dictionary key: Integer(0)",
            )),
        );
    }

    #[test]
    fn serialize_struct() {
        test(
            Struct { a: 1, c: 2, b: 3 },
            Ok(vd([(b"a", vi(1)), (b"c", vi(2)), (b"b", vi(3))])),
        );
        test(Ignored { x: 1, ignored: 2 }, Ok(vd([(b"x", vi(1))])));
    }

    #[test]
    fn serialize_struct_variant() {
        test(
            Enum::Struct { a: 1, c: 2, b: 3 },
            Ok(vd([(
                b"Struct",
                vd([(b"a", vi(1)), (b"c", vi(2)), (b"b", vi(3))]),
            )])),
        );
    }

    #[test]
    fn nested() {
        test(vec![vec![vec![0u8]]], Ok(vl([vl([vl([vi(0)])])])));

        test(
            HashMap::from([("a", HashMap::from([("b", HashMap::from([("c", "d")]))]))]),
            Ok(vd([(b"a", vd([(b"b", vd([(b"c", vb(b"d"))]))]))])),
        );

        test(
            HashMap::from([(
                "a",
                vec![HashMap::from([("b", vec![HashMap::from([("c", "d")])])])],
            )]),
            Ok(vd([(
                b"a",
                vl([vd([(b"b", vl([vd([(b"c", vb(b"d"))])]))])]),
            )])),
        );
    }

    #[test]
    fn flatten() {
        test(
            Flatten {
                a: 1,
                c: 2,
                b: 3,
                rest: vd([(b"x", vi(4)), (b"y", vb(b"spam egg"))]).to_own(),
            },
            Ok(vd([
                (b"a", vi(1)),
                (b"c", vi(2)),
                (b"b", vi(3)),
                (b"x", vi(4)),
                (b"y", vb(b"spam egg")),
            ])),
        );

        // `serde(flatten)` does not support serialization from a sequence.
        assert_matches!(
            Flatten {
                a: 1,
                c: 2,
                b: 3,
                rest: vl([]).to_own(),
            }
            .serialize(Serializer::<Bytes>::new()),
            Err(_),
        );
    }
}
