use std::fmt;
use std::marker::PhantomData;

use serde::de::{self, Deserialize, Deserializer, MapAccess, SeqAccess};

use crate::bstr::{DeserializableBStr, OwnedBStr};

use super::int::FromInt;
use super::{Dictionary, Integer, List, Value};

impl<'de, B> Deserialize<'de> for Value<B>
where
    B: Deserialize<'de>,
    B: OwnedBStr,
{
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(Visitor::new())
    }
}

impl<'de: 'a, 'a> Deserialize<'de> for Value<&'a [u8]> {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(Visitor::new())
    }
}

pub(crate) struct Visitor<B>(PhantomData<B>);

impl<B> Visitor<B> {
    pub(crate) fn new() -> Self {
        Self(PhantomData)
    }
}

impl<'de, B> de::Visitor<'de> for Visitor<B>
where
    Value<B>: Deserialize<'de>,
    B: Deserialize<'de>,
    B: DeserializableBStr<'de>,
{
    type Value = Value<B>;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("any valid bencode value")
    }

    fn visit_bytes<E>(self, value: &[u8]) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        B::from_bytes(value).map(Value::ByteString)
    }

    fn visit_byte_buf<E>(self, value: Vec<u8>) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        B::from_byte_buf(value).map(Value::ByteString)
    }

    fn visit_borrowed_bytes<E>(self, value: &'de [u8]) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        B::from_borrowed_bytes(value).map(Value::ByteString)
    }

    fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::Integer(value))
    }

    fn visit_seq<A>(self, mut seq: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut list = List::with_capacity(seq.size_hint().unwrap_or(0));
        while let Some(item) = seq.next_element()? {
            list.push(item);
        }
        Ok(Value::List(list))
    }

    fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut dict = Dictionary::new();
        while let Some((key, value)) = map.next_entry()? {
            dict.insert(key, value);
        }
        Ok(Value::Dictionary(dict))
    }

    //
    // Our deserializer should not invoke the visitor methods below, but we implement them anyway
    // so that `Visitor` can work with deserializers for other data formats.  (I am not sure if
    // this is a good idea.)
    //

    fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::Integer(value.into()))
    }

    fn visit_i128<E>(self, value: i128) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Integer::de_from_int(value).map(Value::Integer)
    }

    fn visit_u8<E>(self, value: u8) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::Integer(value.into()))
    }

    fn visit_u16<E>(self, value: u16) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::Integer(value.into()))
    }

    fn visit_u32<E>(self, value: u32) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::Integer(value.into()))
    }

    fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Integer::de_from_int(value).map(Value::Integer)
    }

    fn visit_u128<E>(self, value: u128) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Integer::de_from_int(value).map(Value::Integer)
    }

    fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::Integer(value as Integer))
    }

    fn visit_str<E>(self, value: &str) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        self.visit_bytes(value.as_bytes())
    }

    fn visit_string<E>(self, value: String) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        self.visit_byte_buf(value.into())
    }

    fn visit_borrowed_str<E>(self, value: &'de str) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        self.visit_borrowed_bytes(value.as_bytes())
    }

    fn visit_none<E>(self) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::List([].into()))
    }

    fn visit_some<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        Ok(Value::List([deserializer.deserialize_any(self)?].into()))
    }

    fn visit_unit<E>(self) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(Value::List([].into()))
    }

    fn visit_newtype_struct<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(self)
    }

    // We cannot actually implement `visit_enum` for `Value` because `Value` represents any valid
    // Bencode value and we cannot make any assumptions about the structure of the input data.
    // ```
    // fn visit_enum<A>(self, data: A) -> Result<Self::Value, A::Error>
    // where
    //     A: EnumAccess<'de>,
    // {
    //     ...
    // }
    // ```
}

#[cfg(test)]
mod tests {
    use std::any;
    use std::collections::HashMap;

    use bytes::Bytes;
    use serde::de::value::{BorrowedBytesDeserializer, BorrowedStrDeserializer, Error};
    use serde::de::{Error as _, IntoDeserializer};

    use crate::int::Int;
    use crate::testing::{
        ByteBufDeserializer, NewtypeStructDeserializer, OptionDeserializer, UnitEnumAccess, vb, vd,
        vi, vl,
    };

    use super::*;

    fn test<'de, T>(testdata: T, expect: Result<Value<&'_ [u8]>, Error>)
    where
        T: IntoDeserializer<'de>,
    {
        assert_eq!(Value::deserialize(testdata.into_deserializer()), expect);
    }

    fn test_own<T>(testdata: T, expect: Result<Value<&'_ [u8]>, Error>)
    where
        T: for<'de> IntoDeserializer<'de>,
    {
        assert_eq!(
            Value::deserialize(testdata.into_deserializer()),
            expect.map(|value| value.to_own::<Bytes>()),
        );
    }

    #[test]
    fn visit_bool() {
        test(true, Ok(Value::Integer(1)));
        test(false, Ok(Value::Integer(0)));
    }

    #[test]
    fn visit_int() {
        fn test_ok<'de, I>(int: I)
        where
            I: IntoDeserializer<'de>,
            I: Int + Into<Integer>,
        {
            test(int, Ok(Value::Integer(int.into())));
        }

        fn test_err<'de, I>(int: I)
        where
            I: IntoDeserializer<'de>,
            I: Int,
        {
            test(
                int,
                Err(Error::custom(std::format!(
                    "{}-to-i64 overflow: {}",
                    any::type_name::<I>(),
                    int,
                ))),
            );
        }

        test_ok(i8::MIN);
        test_ok(i8::MAX);
        test_ok(i16::MIN);
        test_ok(i16::MAX);
        test_ok(i32::MIN);
        test_ok(i32::MAX);
        test_ok(i64::MIN);
        test_ok(i64::MAX);

        let x = i128::from(i64::MIN);
        test(x, Ok(Value::Integer(i64::MIN)));
        test_err(x - 1);
        let x = i128::from(i64::MAX);
        test(x, Ok(Value::Integer(i64::MAX)));
        test_err(x + 1);

        test_ok(u8::MAX);
        test_ok(u16::MAX);
        test_ok(u32::MAX);

        let x = u64::try_from(i64::MAX).unwrap();
        test(x, Ok(Value::Integer(i64::MAX)));
        test_err(x + 1);

        let x = u128::try_from(i64::MAX).unwrap();
        test(x, Ok(Value::Integer(i64::MAX)));
        test_err(x + 1);
    }

    #[test]
    fn visit_float() {
        test(1.5f32, Ok(Value::Integer(1)));
        test(1.5f64, Ok(Value::Integer(1)));
    }

    #[test]
    fn visit_char() {
        test_own('A', Ok(Value::ByteString(b"A")));
        test_own('\u{2764}', Ok(Value::ByteString(b"\xe2\x9d\xa4")));
        test_own('\x00', Ok(Value::ByteString(b"\x00")));

        test(
            'A',
            Err(Error::custom("borrow from transient byte string: b\"A\"")),
        );
    }

    #[test]
    fn visit_str() {
        fn test_str(testdata: &str) {
            let expect = Value::ByteString(testdata.as_bytes());
            test(BorrowedStrDeserializer::new(testdata), Ok(expect.clone()));
            test_own(testdata, Ok(expect.clone()));
            test_own(testdata.to_string(), Ok(expect));
        }

        test_str("");
        test_str("hello world");
        test_str("\u{2764}");
        test_str("\x00");

        test(
            "",
            Err(Error::custom("borrow from transient byte string: b\"\"")),
        );
        test(
            "".to_string(),
            Err(Error::custom("borrow from owned byte string: b\"\"")),
        );
    }

    #[test]
    fn visit_bytes() {
        fn test_bytes(testdata: &[u8]) {
            let expect = Value::ByteString(testdata);
            test(BorrowedBytesDeserializer::new(testdata), Ok(expect.clone()));
            test_own(testdata, Ok(expect.clone()));
            test_own(ByteBufDeserializer::new(testdata.to_vec()), Ok(expect));
        }

        test_bytes(b"");
        test_bytes(b"hello world");
        test_bytes(b"\xe2\x9d\xa4");
        test_bytes(b"\x00");

        test(
            b"".as_slice(),
            Err(Error::custom("borrow from transient byte string: b\"\"")),
        );
        test(
            ByteBufDeserializer::new(b"".to_vec()),
            Err(Error::custom("borrow from owned byte string: b\"\"")),
        );
    }

    #[test]
    fn visit_option() {
        test(OptionDeserializer::<u8, _>::new(Some(0)), Ok(vl([vi(0)])));
        test(OptionDeserializer::<u8, _>::new(None), Ok(vl([])));
    }

    #[test]
    fn visit_unit() {
        test((), Ok(vl([])));
    }

    #[test]
    fn visit_newtype_struct() {
        test(NewtypeStructDeserializer::new(42u8), Ok(Value::Integer(42)));
        test(NewtypeStructDeserializer::new(()), Ok(vl([])));
    }

    #[test]
    fn visit_seq() {
        test(Vec::<&str>::new(), Ok(vl([])));
        test_own(vec![""], Ok(vl([vb(b"")])));
        test_own(vec!["", "spam egg"], Ok(vl([vb(b""), vb(b"spam egg")])));

        test(vec![BorrowedStrDeserializer::new("")], Ok(vl([vb(b"")])));
        test(
            vec![""],
            Err(Error::custom("borrow from transient byte string: b\"\"")),
        );
    }

    #[test]
    fn visit_map() {
        test(HashMap::<&str, u8>::new(), Ok(vd([])));
        test_own(HashMap::from([("k1", 1u8)]), Ok(vd([(b"k1", vi(1))])));
        test_own(
            HashMap::from([("k1", 1u8), ("k2", 2u8)]),
            Ok(vd([(b"k1", vi(1)), (b"k2", vi(2))])),
        );

        test_own(
            HashMap::from([(0u8, 1u8)]),
            Err(Error::custom(
                "invalid type: integer `0`, expected byte array",
            )),
        );
    }

    #[test]
    fn visit_enum() {
        test(
            UnitEnumAccess::new(),
            Err(Error::custom(
                "invalid type: enum, expected any valid bencode value",
            )),
        );
    }
}
