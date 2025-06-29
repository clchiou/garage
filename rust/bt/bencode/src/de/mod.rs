pub(crate) mod read;
pub(crate) mod strict;

mod dict;
mod enum_;
mod list;

use std::io;
use std::marker::PhantomData;
use std::mem;

use bytes::Buf;
use serde::de::{self, Deserialize, DeserializeOwned, Visitor};

use crate::bstr::DeserializableBStr;
use crate::de_ext::VisitorExt;
use crate::error::io::Error as IoError;
use crate::error::{self, Error};
use crate::int::Int;
use crate::raw::MAGIC;
use crate::raw::de::RawTupleDeserializer;

use self::dict::DictionaryDeserializer;
use self::enum_::{EnumDeserializer, UnitVariantDeserializer};
use self::list::ListDeserializer;
use self::read::{Read, ReadExt, SliceReader, Tee, Token};
use self::strict::{NonStrict, Strict, Strictness};

pub fn from_buf<B, T>(buf: B) -> Result<T, Error>
where
    B: Buf,
    T: DeserializeOwned,
{
    T::deserialize(&mut Deserializer::new(buf))
}

pub fn from_buf_strict<B, T>(buf: B) -> Result<T, Error>
where
    B: Buf,
    T: DeserializeOwned,
{
    T::deserialize(&mut Deserializer::new_strict(buf))
}

pub fn from_slice<'de, T>(slice: &mut &'de [u8]) -> Result<T, Error>
where
    T: Deserialize<'de>,
{
    T::deserialize(&mut Deserializer::new(SliceReader::new(slice)))
}

pub fn from_slice_strict<'de, T>(slice: &mut &'de [u8]) -> Result<T, Error>
where
    T: Deserialize<'de>,
{
    T::deserialize(&mut Deserializer::new_strict(SliceReader::new(slice)))
}

pub fn from_reader<R, T>(reader: R) -> Result<Option<T>, IoError>
where
    R: io::Read,
    T: DeserializeOwned,
{
    check_eof(T::deserialize(&mut Deserializer::new(reader)))
}

pub fn from_reader_strict<R, T>(reader: R) -> Result<Option<T>, IoError>
where
    R: io::Read,
    T: DeserializeOwned,
{
    check_eof(T::deserialize(&mut Deserializer::new_strict(reader)))
}

fn check_eof<T>(result: Result<T, IoError>) -> Result<Option<T>, IoError> {
    use error::de::Error as _;

    match result {
        Ok(value) => Ok(Some(value)),
        Err(error) if error.is_eof() => Ok(None),
        Err(error) => Err(error),
    }
}

pub(crate) struct Deserializer<R, E, S> {
    reader: R,
    state: State,
    _phantom: PhantomData<(E, S)>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum State {
    // To detect `Eof` vs `Incomplete`.
    First,
    Peek(Token),
    None,
}

impl<R, E> Deserializer<R, E, NonStrict> {
    fn new(reader: R) -> Self {
        Self {
            reader,
            state: State::First,
            _phantom: PhantomData,
        }
    }
}

impl<R, E> Deserializer<R, E, Strict> {
    fn new_strict(reader: R) -> Self {
        Self {
            reader,
            state: State::First,
            _phantom: PhantomData,
        }
    }
}

impl<'de, R, E, S> Deserializer<R, E, S>
where
    R: Read<'de, E>,
    E: error::de::Error,
{
    fn tee(&mut self) -> Deserializer<R::Tee<'_>, E, S> {
        let mut reader = self.reader.tee();
        let state = mem::replace(&mut self.state, State::None);
        if let State::Peek(token) = &state {
            reader.unread_u8(token.to_prefix());
        }
        Deserializer {
            reader,
            state,
            _phantom: PhantomData,
        }
    }
}

impl<'de, R, E, S> Deserializer<R, E, S>
where
    R: Tee<'de>,
{
    pub(crate) fn into_bytes(self) -> R::Bytes {
        self.reader.into_bytes()
    }
}

impl<'de, R, E, S> Deserializer<R, E, S>
where
    R: ReadExt<'de, S, E>,
    E: error::de::Error,
    S: Strictness,
{
    fn deserialize_token(&mut self) -> Result<Token, E> {
        match mem::replace(&mut self.state, State::None) {
            State::First => self.reader.read_first_token(),
            State::Peek(token) => Ok(token),
            State::None => self.reader.read_token(),
        }
    }

    fn deserialize_item_token(&mut self) -> Result<Option<Token>, E> {
        match mem::replace(&mut self.state, State::None) {
            State::First => std::panic!("read item when state == first"),
            State::Peek(token) => Ok(Some(token)),
            State::None => self.reader.read_item_token(),
        }
    }

    fn undeserialize_token(&mut self, token: Token) {
        assert_eq!(self.state, State::None);
        self.state = State::Peek(token);
    }

    fn deserialize_byte_string<V>(&mut self, visitor: &V) -> Result<R::Bytes, E>
    where
        V: Visitor<'de>,
    {
        match self.deserialize_token()? {
            Token::ByteString(b0) => self.reader.read_byte_string(b0),
            token => Err(E::invalid_type(token.to_unexpected(), visitor)),
        }
    }

    fn deserialize_integer<V, I>(&mut self, visitor: &V) -> Result<I, E>
    where
        V: Visitor<'de>,
        I: Int,
    {
        match self.deserialize_token()? {
            Token::Integer => self.reader.read_integer(),
            token => Err(E::invalid_type(token.to_unexpected(), visitor)),
        }
    }

    fn deserialize_list_begin<'a, V>(
        &'a mut self,
        visitor: &V,
    ) -> Result<ListDeserializer<'a, R, E, S>, E>
    where
        V: Visitor<'de>,
    {
        match self.deserialize_token()? {
            Token::List => Ok(ListDeserializer::new(self)),
            token => Err(E::invalid_type(token.to_unexpected(), visitor)),
        }
    }
}

impl<'de, R, E, S> de::Deserializer<'de> for &mut Deserializer<R, E, S>
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
        match self.deserialize_token()? {
            Token::ByteString(b0) => self.reader.read_byte_string(b0)?.apply_visit_bytes(visitor),
            Token::Integer => visitor.visit_i64(self.reader.read_integer()?),
            Token::List => Ok(visitor.visit_seq(&mut ListDeserializer::new(self))?),
            Token::Dictionary => Ok(visitor.visit_map(&mut DictionaryDeserializer::new(self))?),
        }
    }

    fn deserialize_bool<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer(&visitor)?;
        visitor.visit_bool_i64(value)
    }

    fn deserialize_i8<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer(&visitor)?;
        visitor.visit_i8(value)
    }

    fn deserialize_i16<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer(&visitor)?;
        visitor.visit_i16(value)
    }

    fn deserialize_i32<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer(&visitor)?;
        visitor.visit_i32(value)
    }

    fn deserialize_i64<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer(&visitor)?;
        visitor.visit_i64(value)
    }

    fn deserialize_i128<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer(&visitor)?;
        visitor.visit_i128(value)
    }

    fn deserialize_u8<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer(&visitor)?;
        visitor.visit_u8(value)
    }

    fn deserialize_u16<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer(&visitor)?;
        visitor.visit_u16(value)
    }

    fn deserialize_u32<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer(&visitor)?;
        visitor.visit_u32(value)
    }

    fn deserialize_u64<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer(&visitor)?;
        visitor.visit_u64(value)
    }

    fn deserialize_u128<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer(&visitor)?;
        visitor.visit_u128(value)
    }

    fn deserialize_f32<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer::<_, i64>(&visitor)?;
        visitor.visit_f32(value as f32)
    }

    fn deserialize_f64<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let value = self.deserialize_integer::<_, i64>(&visitor)?;
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
        let mut list = self.deserialize_list_begin(&visitor)?;
        match list.deserialize_item()? {
            Some(deserializer) => {
                let v = visitor.visit_some(deserializer)?;
                list.deserialize_end(1)?;
                Ok(v)
            }
            None => visitor.visit_none(),
        }
    }

    fn deserialize_unit<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        self.deserialize_list_begin(&visitor)?.deserialize_end(0)?;
        visitor.visit_unit()
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
            visitor.visit_seq(RawTupleDeserializer::new(self.tee()))
        } else {
            visitor.visit_newtype_struct(self)
        }
    }

    fn deserialize_tuple<V>(self, len: usize, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        let mut list = self.deserialize_list_begin(&visitor)?;
        let v = visitor.visit_seq(&mut list)?;
        list.deserialize_end(len)?;
        Ok(v)
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
        match self.deserialize_token()? {
            Token::List => {
                let mut list = ListDeserializer::new(self);
                let v = visitor.visit_seq(&mut list)?;
                list.deserialize_end(fields.len())?;
                Ok(v)
            }
            Token::Dictionary => Ok(visitor.visit_map(&mut DictionaryDeserializer::new(self))?),
            token => Err(E::invalid_type(token.to_unexpected(), &visitor)),
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
        let token = self.deserialize_token()?;
        match token {
            Token::ByteString(_) => {
                self.undeserialize_token(token);
                visitor.visit_enum(UnitVariantDeserializer::new(self))
            }
            Token::Dictionary => {
                let mut dict = DictionaryDeserializer::new(self);
                let v = visitor.visit_enum(EnumDeserializer::new(&mut dict))?;
                dict.deserialize_end(1)?;
                Ok(v)
            }
            _ => Err(E::invalid_type(token.to_unexpected(), &visitor)),
        }
    }

    fn deserialize_identifier<V>(self, visitor: V) -> Result<V::Value, Self::Error>
    where
        V: Visitor<'de>,
    {
        self.deserialize_byte_string(&visitor)?
            .apply_visit_bytes(visitor)
    }

    serde::forward_to_deserialize_any! {
        str string
        bytes byte_buf
        seq
        map
        ignored_any
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::collections::HashMap;
    use std::fmt;

    use bytes::Bytes;

    use crate::testing::{
        Enum, Flatten, Ignored, Newtype, StrictEnum, StrictStruct, Struct, Tuple, Unit, vb, vd, vi,
    };

    use super::*;

    macro_rules! test_matches {
        ($testdata:expr, $type:ty, $($arg:tt)+) => {{
            let mut testdata: &[u8] = $testdata;
            assert_matches!(
                <$type>::deserialize(&mut Deserializer::new_strict(SliceReader::new(
                    &mut testdata,
                ))),
                $($arg)+
            );
        }};
    }

    fn test<'de, T>(testdata: &'de [u8], expect: Result<T, Error>)
    where
        T: de::Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        {
            let mut testdata = testdata;
            assert_eq!(
                T::deserialize(&mut Deserializer::new_strict(SliceReader::new(
                    &mut testdata,
                ))),
                expect,
            );
            assert!(testdata.is_empty());
        }

        {
            let mut testdata = &testdata[..testdata.len() - 1];
            assert_eq!(
                T::deserialize(&mut Deserializer::new_strict(SliceReader::new(
                    &mut testdata,
                ))),
                Err(Error::Incomplete),
            );
        }
    }

    fn test_non_strict<'de, T>(mut testdata: &'de [u8], expect: Result<T, Error>)
    where
        T: de::Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        assert_eq!(
            T::deserialize(&mut Deserializer::new(SliceReader::new(&mut testdata))),
            expect,
        );
    }

    fn test_own<T>(testdata: &[u8], expect: Result<T, Error>)
    where
        T: de::DeserializeOwned,
        T: fmt::Debug + PartialEq,
    {
        assert_eq!(
            T::deserialize(&mut Deserializer::new_strict(Bytes::copy_from_slice(
                testdata,
            ))),
            expect,
        );
    }

    fn test_invalid_type<'de, T>(testdata: &'de [u8])
    where
        T: de::Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        test_err::<T>(testdata, "invalid type: ")
    }

    fn test_invalid_value<'de, T>(testdata: &'de [u8])
    where
        T: de::Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        test_err::<T>(testdata, "invalid value: ")
    }

    fn test_invalid_length<'de, T>(testdata: &'de [u8])
    where
        T: de::Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        test_err::<T>(testdata, "invalid length ")
    }

    fn test_missing_field<'de, T>(testdata: &'de [u8])
    where
        T: de::Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        test_err::<T>(testdata, "missing field ")
    }

    fn test_unknown_field<'de, T>(testdata: &'de [u8])
    where
        T: de::Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        test_err::<T>(testdata, "unknown field ")
    }

    fn test_err<'de, T>(mut testdata: &'de [u8], prefix: &str)
    where
        T: de::Deserialize<'de>,
        T: fmt::Debug + PartialEq,
    {
        assert_matches!(
            T::deserialize(&mut Deserializer::new_strict(SliceReader::new(&mut testdata))),
            Err(error) if error.to_string().starts_with(prefix),
            "prefix = {prefix:?}",
        );
    }

    #[test]
    fn eof() {
        assert_eq!(from_buf::<_, ()>(Bytes::from_static(b"")), Err(Error::Eof));
        assert_eq!(from_slice::<()>(&mut b"".as_slice()), Err(Error::Eof));
        assert_matches!(
            from_reader::<_, ()>(Bytes::from_static(b"").reader()),
            Ok(None),
        );
    }

    #[test]
    fn deserialize_bool() {
        test(b"i1e", Ok(true));
        test(b"i0e", Ok(false));
        test_invalid_type::<bool>(b"0:");
        test_invalid_value::<bool>(b"i2e");

        test_matches!(b"i-0e", bool, Err(Error::StrictInteger { .. }));
        test_matches!(b"i00e", bool, Err(Error::StrictInteger { .. }));
        test_matches!(b"i01e", bool, Err(Error::StrictInteger { .. }));
        test_non_strict(b"i-0e", Ok(false));
        test_non_strict(b"i00e", Ok(false));
        test_non_strict(b"i01e", Ok(true));
    }

    #[test]
    fn deserialize_int() {
        test(b"i-1e", Ok(-1i8));
        test(b"i-1e", Ok(-1i16));
        test(b"i-1e", Ok(-1i32));
        test(b"i-1e", Ok(-1i64));
        test(b"i-1e", Ok(-1i128));

        test(b"i42e", Ok(42u8));
        test(b"i42e", Ok(42u16));
        test(b"i42e", Ok(42u32));
        test(b"i42e", Ok(42u64));
        test(b"i42e", Ok(42u128));

        test_invalid_type::<i8>(b"0:");
        test_invalid_type::<i16>(b"0:");
        test_invalid_type::<i32>(b"0:");
        test_invalid_type::<i64>(b"0:");
        test_invalid_type::<i128>(b"0:");

        test_invalid_type::<u8>(b"0:");
        test_invalid_type::<u16>(b"0:");
        test_invalid_type::<u32>(b"0:");
        test_invalid_type::<u64>(b"0:");
        test_invalid_type::<u128>(b"0:");

        test_matches!(b"i-129e", i8, Err(Error::IntegerOverflow { .. }));
        test_matches!(b"i128e", i8, Err(Error::IntegerOverflow { .. }));
        let testdata = std::format!("i{}e", i128::from(i64::MIN) - 1);
        test_matches!(testdata.as_bytes(), i64, Err(Error::IntegerOverflow { .. }));

        test_matches!(b"i-1e", u8, Err(Error::IntegerOverflow { .. }));
        test_matches!(b"i256e", u8, Err(Error::IntegerOverflow { .. }));
        let testdata = std::format!("i{}e", u128::from(u64::MAX) + 1);
        test_matches!(testdata.as_bytes(), u64, Err(Error::IntegerOverflow { .. }));

        test_matches!(b"i-0e", i8, Err(Error::StrictInteger { .. }));
        test_matches!(b"i00e", i8, Err(Error::StrictInteger { .. }));
        test_matches!(b"i01e", i8, Err(Error::StrictInteger { .. }));
        test_non_strict(b"i-0e", Ok(0i8));
        test_non_strict(b"i00e", Ok(0i8));
        test_non_strict(b"i01e", Ok(1i8));
    }

    #[test]
    fn deserialize_float() {
        test(b"i1e", Ok(1.0f32));
        test(b"i2e", Ok(2.0f64));
    }

    #[test]
    fn deserialize_char() {
        test(b"1:A", Ok('A'));
        test(b"3:\xe2\x9d\xa4", Ok('\u{2764}'));
        test_invalid_type::<char>(b"i0e");
        test_invalid_value::<char>(b"0:");
        test_invalid_value::<char>(b"1:\x80");
        test_invalid_value::<char>(b"2:AB");
    }

    #[test]
    fn deserialize_str() {
        fn test_str(expect: &str) {
            let testdata = std::format!("{}:{}", expect.as_bytes().len(), expect);
            let testdata = testdata.as_bytes();
            test(testdata, Ok(expect));
            test_own(testdata, Ok(expect.to_string()));
        }

        test_str("");
        test_str("hello world");
        test_str("\u{2764}");
        test_str("\x00");

        test_invalid_type::<&str>(b"i0e");
        test_invalid_value::<&str>(b"1:\x80");
    }

    #[test]
    fn deserialize_bytes() {
        fn test_bytes(expect: &[u8]) {
            let mut testdata = <Vec<u8>>::from(std::format!("{}:", expect.len()));
            testdata.extend_from_slice(expect);
            test(&testdata, Ok(expect));
            test_own(&testdata, Ok(Bytes::copy_from_slice(expect)));
        }

        test_bytes(b"");
        test_bytes(b"hello world");
        test_bytes(b"\xe2\x9d\xa4");
        test_bytes(b"\x00");

        test_invalid_type::<&[u8]>(b"i0e");
    }

    #[test]
    fn deserialize_option() {
        test(b"li1ee", Ok(Some(1u8)));
        test(b"le", Ok(None::<u8>));
        test_invalid_type::<Option<u8>>(b"i0e");
        test_invalid_length::<Option<u8>>(b"li1ei2ee");
    }

    #[test]
    fn deserialize_unit() {
        test(b"le", Ok(()));
        test_invalid_type::<()>(b"i0e");
        test_invalid_length::<()>(b"li0ee");
    }

    #[test]
    fn deserialize_unit_struct() {
        test(b"le", Ok(Unit));
        test_invalid_type::<Unit>(b"i0e");
        test_invalid_length::<Unit>(b"li0ee");
    }

    #[test]
    fn deserialize_newtype_struct() {
        test(b"3:\xe2\x9d\xa4", Ok(Newtype("\u{2764}".to_string())));
        test_invalid_type::<Newtype>(b"i0e");
        test_invalid_value::<Newtype>(b"1:\x80");
    }

    #[test]
    fn deserialize_seq() {
        test(b"le", Ok(Vec::<u8>::new()));
        test(b"li42ee", Ok(vec![42u8]));
        test_invalid_type::<Vec<u8>>(b"de");
    }

    #[test]
    fn deserialize_tuple() {
        test(b"li1e1:xe", Ok((1u8, "x")));
        test_invalid_length::<(u8, u8)>(b"li1ee");
        test_invalid_length::<(u8,)>(b"li1ei2ee");

        test_invalid_type::<(u8,)>(b"de");
        test_invalid_type::<(u8, &str)>(b"l1:xi1ee");
    }

    #[test]
    fn deserialize_tuple_struct() {
        test(b"li1e1:xe", Ok(Tuple(1, "x".to_string())));
        test_invalid_length::<Tuple>(b"li1ee");
        test_invalid_length::<Tuple>(b"li1e1:xi2ee");

        test_invalid_type::<Tuple>(b"de");
        test_invalid_type::<Tuple>(b"l1:xi1ee");
    }

    #[test]
    fn deserialize_map() {
        test(b"de", Ok(HashMap::<&str, u8>::from([])));
        test(b"d2:k1i1ee", Ok(HashMap::from([("k1", 1u8)])));
        test(
            b"d2:k1i1e2:k2i2ee",
            Ok(HashMap::from([("k1", 1u8), ("k2", 2u8)])),
        );

        test_invalid_type::<HashMap<&str, u8>>(b"i0e");

        test_matches!(b"di1ei2ee", HashMap<u8, u8>, Err(Error::KeyType { .. }));

        test_matches!(b"d1:ke", HashMap<&str, u8>, Err(Error::MissingValue { .. }));

        test_matches!(
            b"d2:bbi2e3:aaai1e1:ci3ee",
            HashMap<&str, u8>,
            Err(Error::StrictDictionaryKey { .. }),
        );
        test_non_strict(
            b"d2:bbi2e3:aaai1e1:ci3ee",
            Ok(HashMap::from([("aaa", 1u8), ("bb", 2u8), ("c", 3u8)])),
        );
        test_matches!(
            b"d1:ki1e1:ki3e1:ki2ee",
            HashMap<&str, u8>,
            Err(Error::StrictDictionaryKey { .. }),
        );
        test_non_strict(b"d1:ki1e1:ki3e1:ki2ee", Ok(HashMap::from([("k", 2u8)])));
    }

    #[test]
    fn deserialize_struct() {
        let dict = b"d1:ai1e1:bi3e1:ci2e1:xi4ee";
        test(dict, Ok(Struct { a: 1, c: 2, b: 3 }));
        test_missing_field::<Struct>(b"de");
        test_unknown_field::<StrictStruct>(dict);

        test(b"li1ei2ei3ee", Ok(Struct { a: 1, c: 2, b: 3 }));
        test_invalid_length::<Struct>(b"li0ei0ee");
        test_invalid_length::<Struct>(b"li0ei0ei0ei0ee");

        test_invalid_type::<Struct>(b"i0e");
    }

    #[test]
    fn deserialize_enum() {
        test_invalid_type::<Enum>(b"i0e");
        test_invalid_length::<Enum>(b"d7:Newtype0:5:Tupleli0e0:ee");
        test_err::<Enum>(b"1:X", "unknown variant ");
        test_err::<Enum>(b"d1:Xi0ee", "unknown variant ");
    }

    #[test]
    fn deserialize_enum_unit() {
        test(b"4:Unit", Ok(Enum::Unit));
        test_invalid_type::<Enum>(b"d4:Unitlee");
    }

    #[test]
    fn deserialize_enum_newtype() {
        test(
            b"d7:Newtype8:spam egge",
            Ok(Enum::Newtype("spam egg".to_string())),
        );
        test_invalid_type::<Enum>(b"7:Newtype");
    }

    #[test]
    fn deserialize_enum_tuple() {
        test(
            b"d5:Tupleli42e8:spam eggee",
            Ok(Enum::Tuple(42, "spam egg".to_string())),
        );
        test_invalid_length::<Enum>(b"d5:Tupleli0eee");
        test_invalid_length::<Enum>(b"d5:Tupleli0e0:i0eee");

        test_invalid_type::<Enum>(b"5:Tuple");
        test_invalid_type::<Enum>(b"d5:Tupledee");
    }

    #[test]
    fn deserialize_enum_struct() {
        test(
            b"d6:Structd1:ai1e1:bi3e1:ci2e1:xi4eee",
            Ok(Enum::Struct { a: 1, c: 2, b: 3 }),
        );
        test_missing_field::<Enum>(b"d6:Structdee");
        test_unknown_field::<StrictEnum>(b"d6:Structd1:xi42e1:yi0eee");

        test(
            b"d6:Structli1ei2ei3eee",
            Ok(Enum::Struct { a: 1, c: 2, b: 3 }),
        );
        test_invalid_length::<Enum>(b"d6:Structli0ei0eee");
        test_invalid_length::<Enum>(b"d6:Structli0ei0ei0ei0eee");

        test_invalid_type::<Enum>(b"6:Struct");
        test_invalid_type::<Enum>(b"d6:Structi42ee");
    }

    #[test]
    fn deserialize_identifier() {
        test(b"4:Unit", Ok(Enum::Unit));
        test_own(b"4:Unit", Ok(Enum::Unit));
    }

    #[test]
    fn deserialize_ignored_any() {
        test(
            b"d7:ignored13:ignored value1:xi42ee",
            Ok(Ignored { x: 42, ignored: 0 }),
        );
    }

    #[test]
    fn nested() {
        test(b"llli0eeee", Ok(vec![vec![vec![0u8]]]));

        test(
            b"d1:ad1:bd1:c1:deee",
            Ok(HashMap::from([(
                "a",
                HashMap::from([("b", HashMap::from([("c", "d")]))]),
            )])),
        );

        test(
            b"d1:ald1:bld1:c1:deeeee",
            Ok(HashMap::from([(
                "a",
                vec![HashMap::from([("b", vec![HashMap::from([("c", "d")])])])],
            )])),
        );
    }

    #[test]
    fn flatten() {
        test(
            b"d1:ai1e1:bi3e1:ci2e1:xi4e1:y8:spam egge",
            Ok(Flatten {
                a: 1,
                c: 2,
                b: 3,
                rest: vd([(b"x", vi(4)), (b"y", vb(b"spam egg"))]).to_own(),
            }),
        );

        // `serde(flatten)` does not support deserialization from a sequence.
        test_invalid_type::<Flatten>(b"le");
    }
}
