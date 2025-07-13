pub(crate) mod write;

use std::io;
use std::marker::PhantomData;

use bytes::{BufMut, Bytes, BytesMut};
use serde::ser::{
    self, Serialize, SerializeMap, SerializeSeq, SerializeStruct, SerializeStructVariant,
    SerializeTuple, SerializeTupleStruct, SerializeTupleVariant,
};

use crate::error::io::Error as IoError;
use crate::error::{self, Error};
use crate::raw::MAGIC;
use crate::raw::ser::RawDataSerializer;
use crate::value;

use self::write::Write;

pub fn to_buf<B, T>(buf: B, value: &T) -> Result<(), Error>
where
    B: BufMut,
    T: ?Sized + Serialize,
{
    value.serialize(&mut Serializer::new(buf))
}

pub fn to_bytes<T>(value: &T) -> Result<Bytes, Error>
where
    T: ?Sized + Serialize,
{
    let mut buf = BytesMut::new();
    to_buf(&mut buf, value)?;
    Ok(buf.freeze())
}

pub fn to_writer<W, T>(writer: W, value: &T) -> Result<(), IoError>
where
    W: io::Write,
    T: ?Sized + Serialize,
{
    value.serialize(&mut Serializer::new(writer))
}

struct Serializer<W, E>(W, PhantomData<E>);

struct DictionarySerializer<'a, W, E>(&'a mut W, Vec<(Bytes, Option<Bytes>)>, PhantomData<E>);

impl<W, E> Serializer<W, E> {
    fn new(writer: W) -> Self {
        Self(writer, PhantomData)
    }
}

impl<'a, W, E> DictionarySerializer<'a, W, E> {
    fn new(writer: &'a mut W, len: usize) -> Self {
        Self(writer, Vec::with_capacity(len), PhantomData)
    }
}

impl<'a, W, E> ser::Serializer for &'a mut Serializer<W, E>
where
    W: Write<E>,
    E: error::ser::Error,
{
    type Ok = ();
    type Error = E;

    type SerializeSeq = Self;
    type SerializeTuple = Self;
    type SerializeTupleStruct = Self;
    type SerializeTupleVariant = Self;

    type SerializeMap = DictionarySerializer<'a, W, E>;
    type SerializeStruct = DictionarySerializer<'a, W, E>;
    type SerializeStructVariant = DictionarySerializer<'a, W, E>;

    fn serialize_bool(self, value: bool) -> Result<Self::Ok, Self::Error> {
        self.0.write_integer(if value { 1 } else { 0 })
    }

    fn serialize_i8(self, value: i8) -> Result<Self::Ok, Self::Error> {
        self.0.write_integer(value)
    }

    fn serialize_i16(self, value: i16) -> Result<Self::Ok, Self::Error> {
        self.0.write_integer(value)
    }

    fn serialize_i32(self, value: i32) -> Result<Self::Ok, Self::Error> {
        self.0.write_integer(value)
    }

    fn serialize_i64(self, value: i64) -> Result<Self::Ok, Self::Error> {
        self.0.write_integer(value)
    }

    fn serialize_i128(self, value: i128) -> Result<Self::Ok, Self::Error> {
        self.0.write_integer(value)
    }

    fn serialize_u8(self, value: u8) -> Result<Self::Ok, Self::Error> {
        self.0.write_integer(value)
    }

    fn serialize_u16(self, value: u16) -> Result<Self::Ok, Self::Error> {
        self.0.write_integer(value)
    }

    fn serialize_u32(self, value: u32) -> Result<Self::Ok, Self::Error> {
        self.0.write_integer(value)
    }

    fn serialize_u64(self, value: u64) -> Result<Self::Ok, Self::Error> {
        self.0.write_integer(value)
    }

    fn serialize_u128(self, value: u128) -> Result<Self::Ok, Self::Error> {
        self.0.write_integer(value)
    }

    fn serialize_f32(self, value: f32) -> Result<Self::Ok, Self::Error> {
        self.0.write_integer(value as i64)
    }

    fn serialize_f64(self, value: f64) -> Result<Self::Ok, Self::Error> {
        self.0.write_integer(value as i64)
    }

    fn serialize_char(self, value: char) -> Result<Self::Ok, Self::Error> {
        self.0.write_string(value.encode_utf8(&mut [0u8; 4]))
    }

    fn serialize_str(self, value: &str) -> Result<Self::Ok, Self::Error> {
        self.0.write_string(value)
    }

    fn serialize_bytes(self, value: &[u8]) -> Result<Self::Ok, Self::Error> {
        self.0.write_byte_string(value)
    }

    fn serialize_none(self) -> Result<Self::Ok, Self::Error> {
        self.0.write_list_begin()?;
        self.0.write_list_end()
    }

    fn serialize_some<T>(self, value: &T) -> Result<Self::Ok, Self::Error>
    where
        T: ?Sized + Serialize,
    {
        self.0.write_list_begin()?;
        value.serialize(&mut *self)?;
        self.0.write_list_end()
    }

    fn serialize_unit(self) -> Result<Self::Ok, Self::Error> {
        self.0.write_list_begin()?;
        self.0.write_list_end()
    }

    fn serialize_unit_struct(self, _name: &'static str) -> Result<Self::Ok, Self::Error> {
        self.0.write_list_begin()?;
        self.0.write_list_end()
    }

    fn serialize_unit_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
    ) -> Result<Self::Ok, Self::Error> {
        self.0.write_string(variant)
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
            value.serialize(&mut RawDataSerializer::new(&mut self.0))
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
        self.0.write_dictionary_begin()?;
        self.0.write_string(variant)?;
        value.serialize(&mut *self)?;
        self.0.write_dictionary_end()
    }

    fn serialize_seq(self, _len: Option<usize>) -> Result<Self::SerializeSeq, Self::Error> {
        self.0.write_list_begin()?;
        Ok(self)
    }

    fn serialize_tuple(self, _len: usize) -> Result<Self::SerializeTuple, Self::Error> {
        self.0.write_list_begin()?;
        Ok(self)
    }

    fn serialize_tuple_struct(
        self,
        _name: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeTupleStruct, Self::Error> {
        self.0.write_list_begin()?;
        Ok(self)
    }

    fn serialize_tuple_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
        _len: usize,
    ) -> Result<Self::SerializeTupleVariant, Self::Error> {
        self.0.write_dictionary_begin()?;
        self.0.write_string(variant)?;
        self.0.write_list_begin()?;
        Ok(self)
    }

    fn serialize_map(self, len: Option<usize>) -> Result<Self::SerializeMap, Self::Error> {
        self.0.write_dictionary_begin()?;
        Ok(DictionarySerializer::new(&mut self.0, len.unwrap_or(0)))
    }

    fn serialize_struct(
        self,
        _name: &'static str,
        len: usize,
    ) -> Result<Self::SerializeStruct, Self::Error> {
        self.0.write_dictionary_begin()?;
        Ok(DictionarySerializer::new(&mut self.0, len))
    }

    fn serialize_struct_variant(
        self,
        _name: &'static str,
        _variant_index: u32,
        variant: &'static str,
        len: usize,
    ) -> Result<Self::SerializeStructVariant, Self::Error> {
        self.0.write_dictionary_begin()?;
        self.0.write_string(variant)?;
        self.0.write_dictionary_begin()?;
        Ok(DictionarySerializer::new(&mut self.0, len))
    }
}

impl<W, E> SerializeSeq for &mut Serializer<W, E>
where
    W: Write<E>,
    E: error::ser::Error,
{
    type Ok = ();
    type Error = E;

    fn serialize_element<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        value.serialize(&mut **self)
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        self.0.write_list_end()
    }
}

impl<W, E> SerializeTuple for &mut Serializer<W, E>
where
    W: Write<E>,
    E: error::ser::Error,
{
    type Ok = ();
    type Error = E;

    fn serialize_element<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        value.serialize(&mut **self)
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        self.0.write_list_end()
    }
}

impl<W, E> SerializeTupleStruct for &mut Serializer<W, E>
where
    W: Write<E>,
    E: error::ser::Error,
{
    type Ok = ();
    type Error = E;

    fn serialize_field<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        value.serialize(&mut **self)
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        self.0.write_list_end()
    }
}

impl<W, E> SerializeTupleVariant for &mut Serializer<W, E>
where
    W: Write<E>,
    E: error::ser::Error,
{
    type Ok = ();
    type Error = E;

    fn serialize_field<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        value.serialize(&mut **self)
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        self.0.write_list_end()?;
        self.0.write_dictionary_end()
    }
}

impl<'a, W, E> SerializeMap for DictionarySerializer<'a, W, E>
where
    W: Write<E>,
    E: error::ser::Error,
{
    type Ok = ();
    type Error = E;

    fn serialize_key<T>(&mut self, key: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        self.serialize_item::<_, ()>(key, None)
    }

    fn serialize_value<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        self.1.last_mut().expect("item").1 = Some(to_bytes(value)?);
        Ok(())
    }

    fn serialize_entry<K, V>(&mut self, key: &K, value: &V) -> Result<(), Self::Error>
    where
        K: ?Sized + Serialize,
        V: ?Sized + Serialize,
    {
        self.serialize_item(key, Some(value))
    }

    fn end(mut self) -> Result<Self::Ok, Self::Error> {
        self.sort_then_write_items()?;
        self.0.write_dictionary_end()
    }
}

impl<'a, W, E> SerializeStruct for DictionarySerializer<'a, W, E>
where
    W: Write<E>,
    E: error::ser::Error,
{
    type Ok = ();
    type Error = E;

    fn serialize_field<T>(&mut self, key: &'static str, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        self.serialize_item(key, Some(value))
    }

    fn end(mut self) -> Result<Self::Ok, Self::Error> {
        self.sort_then_write_items()?;
        self.0.write_dictionary_end()
    }
}

impl<'a, W, E> SerializeStructVariant for DictionarySerializer<'a, W, E>
where
    W: Write<E>,
    E: error::ser::Error,
{
    type Ok = ();
    type Error = E;

    fn serialize_field<T>(&mut self, key: &'static str, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        self.serialize_item(key, Some(value))
    }

    fn end(mut self) -> Result<Self::Ok, Self::Error> {
        self.sort_then_write_items()?;
        self.0.write_dictionary_end()?;
        self.0.write_dictionary_end()
    }
}

impl<'a, W, E> DictionarySerializer<'a, W, E>
where
    W: Write<E>,
    E: From<Error>,
{
    fn serialize_item<K, V>(&mut self, key: &K, value: Option<&V>) -> Result<(), E>
    where
        K: ?Sized + Serialize,
        V: ?Sized + Serialize,
    {
        let key = value::ser::serialize_key(key)?;
        let serialized_value = value.map(|value| to_bytes(value)).transpose()?;
        self.1.push((key, serialized_value));
        Ok(())
    }

    fn sort_then_write_items(&mut self) -> Result<(), E> {
        self.1.sort_by_key(|(key, _)| key.clone());
        for (key, serialized_value) in self.1.iter() {
            self.0.write_byte_string(key)?;
            self.0
                .write_slice(serialized_value.as_ref().expect("dictionary value"))?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::collections::HashMap;

    use serde::ser::Error as _;

    use crate::int::Int;
    use crate::testing::{
        AdjacentlyTagged, Enum, Flatten, Ignored, InternallyTagged, Newtype, Struct, Tuple, Unit,
        Untagged, vb, vd, vi, vl,
    };

    use super::*;

    fn test<T>(testdata: T, expect: &[u8])
    where
        T: Serialize,
    {
        assert_eq!(to_bytes(&testdata), Ok(Bytes::copy_from_slice(expect)));

        let mut writer = Vec::new();
        to_writer(&mut writer, &testdata).unwrap();
        assert_eq!(writer, expect);
    }

    #[test]
    fn serialize_bool() {
        test(true, b"i1e");
        test(false, b"i0e");
    }

    #[test]
    fn serialize_int() {
        fn test_int<I>(value: I)
        where
            I: Int + Serialize,
        {
            let expect = std::format!("i{value}e");
            test(value, expect.as_bytes());
        }

        test_int(i8::MIN);
        test_int(i8::MAX);
        test_int(i16::MIN);
        test_int(i16::MAX);
        test_int(i32::MIN);
        test_int(i32::MAX);
        test_int(i64::MIN);
        test_int(i64::MAX);
        test_int(i128::MIN);
        test_int(i128::MAX);

        test_int(u8::MIN);
        test_int(u8::MAX);
        test_int(u16::MIN);
        test_int(u16::MAX);
        test_int(u32::MIN);
        test_int(u32::MAX);
        test_int(u64::MIN);
        test_int(u64::MAX);
        test_int(u128::MIN);
        test_int(u128::MAX);

        test(vi(-1), b"i-1e");
    }

    #[test]
    fn serialize_float() {
        test(1.5f32, b"i1e");
        test(2.5f64, b"i2e");
    }

    #[test]
    fn serialize_char() {
        test('A', b"1:A");
        test('\u{2764}', b"3:\xe2\x9d\xa4");
    }

    #[test]
    fn serialize_str() {
        test("", b"0:");
        test("hello world", b"11:hello world");
        test("\u{2764}", b"3:\xe2\x9d\xa4");
        test("\x00", b"1:\x00");
    }

    #[test]
    fn serialize_bytes() {
        use serde_bytes::Bytes;

        test(Bytes::new(b""), b"0:");
        test(Bytes::new(b"hello world"), b"11:hello world");
        test(Bytes::new(b"\xe2\x9d\xa4"), b"3:\xe2\x9d\xa4");
        test(Bytes::new(b"\x00"), b"1:\x00");

        test(vb(b""), b"0:");
        test(vb(b"spam egg"), b"8:spam egg");
    }

    #[test]
    fn serialize_option() {
        test(Some(42u8), b"li42ee");
        test(None::<u8>, b"le");
    }

    #[test]
    fn serialize_unit() {
        test((), b"le");
    }

    #[test]
    fn serialize_unit_struct() {
        test(Unit, b"le");
    }

    #[test]
    fn serialize_unit_variant() {
        test(Enum::Unit, b"4:Unit");
    }

    #[test]
    fn serialize_newtype_struct() {
        test(Newtype("hello world".to_string()), b"11:hello world");
    }

    #[test]
    fn serialize_newtype_variant() {
        test(
            Enum::Newtype("hello world".to_string()),
            b"d7:Newtype11:hello worlde",
        );
    }

    #[test]
    fn serialize_seq() {
        test(Vec::<u8>::new(), b"le");
        test(vec![1u8], b"li1ee");
        test(vec![1u8, 2u8], b"li1ei2ee");

        test(vec![vb(b"spam egg"), vi(42)], b"l8:spam eggi42ee");
        test(vl([vb(b"spam egg"), vi(42)]), b"l8:spam eggi42ee");
    }

    #[test]
    fn serialize_tuple() {
        test((1u8,), b"li1ee");
        test((1u8, "spam egg"), b"li1e8:spam egge");
    }

    #[test]
    fn serialize_tuple_struct() {
        test(Tuple(1u8, "spam egg".to_string()), b"li1e8:spam egge");
    }

    #[test]
    fn serialize_tuple_variant() {
        test(
            Enum::Tuple(1u8, "spam egg".to_string()),
            b"d5:Tupleli1e8:spam eggee",
        );
    }

    #[test]
    fn serialize_map() {
        test(HashMap::<&str, u8>::from([]), b"de");
        test(
            HashMap::from([("k1", 1u8), ("k2", 2u8)]),
            b"d2:k1i1e2:k2i2ee",
        );
        test(
            vd([(b"k1", vi(1)), (b"k2", vb(b"foobar"))]),
            b"d2:k1i1e2:k26:foobare",
        );

        // Items are sorted by raw key byte strings, not by their serialized forms.
        test(
            HashMap::from([("bbbbbbbbbb", 1u8), ("aaa", 2u8), ("cc", 3u8)]),
            b"d3:aaai2e10:bbbbbbbbbbi1e2:cci3ee",
        );

        assert_eq!(
            to_bytes(&HashMap::from([(0u8, 0u8)])),
            Err(Error::custom(
                "expect byte string dictionary key: Integer(0)"
            )),
        );
    }

    #[test]
    fn serialize_struct() {
        test(Struct { a: 1, c: 2, b: 3 }, b"d1:ai1e1:bi3e1:ci2ee");
        test(Ignored { x: 1, ignored: 2 }, b"d1:xi1ee");
    }

    #[test]
    fn serialize_struct_variant() {
        test(
            Enum::Struct { a: 1, c: 2, b: 3 },
            b"d6:Structd1:ai1e1:bi3e1:ci2eee",
        );
    }

    #[test]
    fn nested() {
        test(vec![vec![vec![0u8]]], b"llli0eeee");

        test(
            HashMap::from([("a", HashMap::from([("b", HashMap::from([("c", "d")]))]))]),
            b"d1:ad1:bd1:c1:deee",
        );

        test(
            HashMap::from([(
                "a",
                vec![HashMap::from([("b", vec![HashMap::from([("c", "d")])])])],
            )]),
            b"d1:ald1:bld1:c1:deeeee",
        );
    }

    #[test]
    fn enum_repr() {
        test(
            InternallyTagged::Bool { value: true },
            b"d1:t4:Bool5:valuei1ee",
        );
        test(
            InternallyTagged::Char { value: 'c' },
            b"d1:t4:Char5:value1:ce",
        );

        test(
            AdjacentlyTagged::Bool { value: true },
            b"d1:cd5:valuei1ee1:t4:Boole",
        );
        test(
            AdjacentlyTagged::Char { value: 'c' },
            b"d1:cd5:value1:ce1:t4:Chare",
        );

        test(Untagged::Bool { value: true }, b"d5:valuei1ee");
        test(Untagged::Char { value: 'c' }, b"d5:value1:ce");
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
            b"d1:ai1e1:bi3e1:ci2e1:xi4e1:y8:spam egge",
        );

        // `serde(flatten)` does not support serialization from a sequence.
        assert_matches!(
            to_bytes(&Flatten {
                a: 1,
                c: 2,
                b: 3,
                rest: vl([]).to_own(),
            }),
            Err(_),
        );
    }
}
