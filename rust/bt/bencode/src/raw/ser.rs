use std::marker::PhantomData;

use serde::ser::{self, Impossible, Serialize, SerializeTuple};

use crate::bstr::OwnedBStr;
use crate::error::Error;
use crate::ser::write::Write;
use crate::value::{self, Value};

// `RawTuple = (RawValue, RawData)`
fn expect_raw_tuple<E>() -> E
where
    E: ser::Error,
{
    E::custom("expect (T, D) tuple")
}

macro_rules! impl_serializer {
    () => {
        type SerializeSeq = Impossible<Self::Ok, Self::Error>;
        type SerializeTuple = Self;
        type SerializeTupleStruct = Impossible<Self::Ok, Self::Error>;
        type SerializeTupleVariant = Impossible<Self::Ok, Self::Error>;

        type SerializeMap = Impossible<Self::Ok, Self::Error>;
        type SerializeStruct = Impossible<Self::Ok, Self::Error>;
        type SerializeStructVariant = Impossible<Self::Ok, Self::Error>;

        fn serialize_bool(self, _value: bool) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_i8(self, _value: i8) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_i16(self, _value: i16) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_i32(self, _value: i32) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_i64(self, _value: i64) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_i128(self, _value: i128) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_u8(self, _value: u8) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_u16(self, _value: u16) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_u32(self, _value: u32) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_u64(self, _value: u64) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_u128(self, _value: u128) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_f32(self, _value: f32) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_f64(self, _value: f64) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_char(self, _value: char) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_str(self, _value: &str) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_none(self) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_some<T>(self, _value: &T) -> Result<Self::Ok, Self::Error>
        where
            T: ?Sized + Serialize,
        {
            Err(expect_raw_tuple())
        }

        fn serialize_unit(self) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_unit_struct(self, _name: &'static str) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_unit_variant(
            self,
            _name: &'static str,
            _variant_index: u32,
            _variant: &'static str,
        ) -> Result<Self::Ok, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_newtype_struct<T>(
            self,
            _name: &'static str,
            _value: &T,
        ) -> Result<Self::Ok, Self::Error>
        where
            T: ?Sized + Serialize,
        {
            Err(expect_raw_tuple())
        }

        fn serialize_newtype_variant<T>(
            self,
            _name: &'static str,
            _variant_index: u32,
            _variant: &'static str,
            _value: &T,
        ) -> Result<Self::Ok, Self::Error>
        where
            T: ?Sized + Serialize,
        {
            Err(expect_raw_tuple())
        }

        fn serialize_seq(self, _len: Option<usize>) -> Result<Self::SerializeSeq, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_tuple_struct(
            self,
            _name: &'static str,
            _len: usize,
        ) -> Result<Self::SerializeTupleStruct, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_tuple_variant(
            self,
            _name: &'static str,
            _variant_index: u32,
            _variant: &'static str,
            _len: usize,
        ) -> Result<Self::SerializeTupleVariant, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_map(self, _len: Option<usize>) -> Result<Self::SerializeMap, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_struct(
            self,
            _name: &'static str,
            _len: usize,
        ) -> Result<Self::SerializeStruct, Self::Error> {
            Err(expect_raw_tuple())
        }

        fn serialize_struct_variant(
            self,
            _name: &'static str,
            _variant_index: u32,
            _variant: &'static str,
            _len: usize,
        ) -> Result<Self::SerializeStructVariant, Self::Error> {
            Err(expect_raw_tuple())
        }
    };
}

//
// `RawValueSerializer`
//

pub(crate) struct RawValueSerializer<B>(Option<Value<B>>);

impl<B> RawValueSerializer<B> {
    pub(crate) fn new() -> Self {
        Self(None)
    }
}

impl<B> ser::Serializer for RawValueSerializer<B>
where
    B: OwnedBStr,
{
    type Ok = Value<B>;
    type Error = Error;

    fn serialize_tuple(self, len: usize) -> Result<Self::SerializeTuple, Self::Error> {
        if len == 2 {
            Ok(self)
        } else {
            Err(expect_raw_tuple())
        }
    }

    fn serialize_bytes(self, _value: &[u8]) -> Result<Self::Ok, Self::Error> {
        Err(expect_raw_tuple())
    }

    impl_serializer!();
}

impl<B> SerializeTuple for RawValueSerializer<B>
where
    B: OwnedBStr,
{
    type Ok = Value<B>;
    type Error = Error;

    fn serialize_element<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        if self.0.is_none() {
            self.0 = Some(value.serialize(value::ser::Serializer::new())?);
        }
        Ok(())
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        self.0.ok_or_else(expect_raw_tuple)
    }
}

//
// `RawDataSerializer`
//

pub(crate) struct RawDataSerializer<'a, W, E>(&'a mut W, bool, PhantomData<E>);

impl<'a, W, E> RawDataSerializer<'a, W, E> {
    pub(crate) fn new(writer: &'a mut W) -> Self {
        Self(writer, false, PhantomData)
    }
}

impl<'a, W, E> ser::Serializer for &mut RawDataSerializer<'a, W, E>
where
    W: Write<E>,
    E: ser::Error,
{
    type Ok = ();
    type Error = E;

    fn serialize_tuple(self, len: usize) -> Result<Self::SerializeTuple, Self::Error> {
        if len == 2 {
            Ok(self)
        } else {
            Err(expect_raw_tuple())
        }
    }

    fn serialize_bytes(self, value: &[u8]) -> Result<Self::Ok, Self::Error> {
        if self.1 {
            self.0.write_slice(value)
        } else {
            Err(expect_raw_tuple())
        }
    }

    impl_serializer!();
}

impl<'a, W, E> SerializeTuple for &mut RawDataSerializer<'a, W, E>
where
    W: Write<E>,
    E: ser::Error,
{
    type Ok = ();
    type Error = E;

    fn serialize_element<T>(&mut self, value: &T) -> Result<(), Self::Error>
    where
        T: ?Sized + Serialize,
    {
        if self.1 {
            value.serialize(&mut **self)
        } else {
            self.1 = true;
            Ok(())
        }
    }

    fn end(self) -> Result<Self::Ok, Self::Error> {
        if self.1 {
            Ok(())
        } else {
            Err(expect_raw_tuple())
        }
    }
}
