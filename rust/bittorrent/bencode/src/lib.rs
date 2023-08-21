//! Implementation of Bencode Format as Specified in BEP 3

#![feature(iterator_try_collect)]

pub mod convert;
pub mod dict;
#[cfg(feature = "serde")]
pub mod serde;

use std::collections::BTreeMap;
use std::fmt;
use std::ops::Deref;
use std::str::{self, FromStr};

use bytes::{Buf, BufMut};
use snafu::prelude::*;

use g1_base::fmt::EscapeAscii;
use g1_bytes::{BufMutExt, BufPeekExt, BufSliceExt};

/// Bencode Value
///
/// This is the generic value type.  You should use concrete value types `own::Value` and
/// `borrow::Value`.
#[derive(Clone, Eq, PartialEq)]
pub enum Value<ByteString, List, Dictionary> {
    ByteString(ByteString),
    // BEP 3 does not specify the size of integers.  Let us use i64 for now.
    Integer(i64),
    List(List),
    // Use `BTreeMap` because BEP 3 requires dictionary keys to be sorted.
    Dictionary(Dictionary),
}

pub mod own {
    use std::collections::BTreeMap;

    use bytes::BytesMut;

    use g1_base::ops::{Deref, DerefMut};

    /// Owned Value
    ///
    /// It is constructable and mutable, as it implements both the `From` trait and the `DerefMut`
    /// trait.  If you intend to manipulate a Bencode value, use this type.
    pub type Value = super::Value<ByteString, List, Dictionary>;

    pub type ByteString = BytesMut;

    // We need to create a new type because Rust does not allow recursive type aliases.
    // https://github.com/rust-lang/rfcs/issues/1390
    #[derive(Clone, Deref, DerefMut, Eq, PartialEq)]
    pub struct List(pub(crate) Vec<Value>);

    // Ditto.
    #[derive(Clone, Deref, DerefMut, Eq, PartialEq)]
    pub struct Dictionary(pub(crate) BTreeMap<ByteString, Value>);
}

pub mod borrow {
    use std::collections::BTreeMap;

    use g1_base::{cmp::PartialEqExt, ops::Deref};

    g1_base::define_owner!(
        /// Borrowed Value Container
        ///
        /// It is a container of a borrowed value and the buffer from which the value borrows.
        pub ValueOwner for Value
    );

    /// Borrowed Value
    ///
    /// A borrowed value is constructed by decoding it from a buffer, from which the value borrows.
    /// A borrowed value is read-only, and to manipulate it, you must convert it into an owned
    /// value.
    ///
    /// The borrowed value type supports a feature that the owned value type lacks: The list and
    /// dictionary values store a reference to the raw Bencode data.  You may use the raw data to
    /// compute the checksum of a Bencode value.
    pub type Value<'a> = super::Value<ByteString<'a>, List<'a>, Dictionary<'a>>;

    pub type ByteString<'a> = &'a [u8];

    #[derive(Clone, Deref, Eq, PartialEqExt)]
    pub struct List<'a> {
        #[deref(target)]
        pub(super) list: Vec<Value<'a>>,
        #[partial_eq(skip)]
        pub(super) raw_value: &'a [u8],
    }

    #[derive(Clone, Deref, Eq, PartialEqExt)]
    pub struct Dictionary<'a> {
        #[deref(target)]
        pub(super) dict: BTreeMap<ByteString<'a>, Value<'a>>,
        #[partial_eq(skip)]
        pub(super) raw_value: &'a [u8],
    }
}

/// `Value::decode` error.
#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Error {
    Incomplete,
    #[snafu(display("invalid byte string length: \"{length}\""))]
    InvalidByteStringLength {
        length: String,
    },
    #[snafu(display("invalid integer: \"{integer}\""))]
    InvalidInteger {
        integer: String,
    },
    #[snafu(display("invalid value type: {value_type}"))]
    InvalidValueType {
        value_type: u8,
    },
    #[snafu(display("not strictly increasing dictionary key: \"{last_key}\" >= \"{new_key}\""))]
    NotStrictlyIncreasingDictionaryKey {
        last_key: String,
        new_key: String,
    },
    #[snafu(display(
        "unexpected trailing data: value={value:?} trailing_data=\"{trailing_data}\"",
    ))]
    UnexpectedTrailingData {
        value: own::Value,
        trailing_data: String,
    },
}

impl<ByteString, List, Dictionary> fmt::Debug for Value<ByteString, List, Dictionary>
where
    ByteString: AsRef<[u8]>,
    List: fmt::Debug,
    Dictionary: fmt::Debug,
{
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ByteString(bytes) => f
                .debug_tuple("ByteString")
                .field(&EscapeAscii(bytes.as_ref()))
                .finish(),
            Self::Integer(int) => f.debug_tuple("Integer").field(int).finish(),
            Self::List(list) => f.debug_tuple("List").field(list).finish(),
            Self::Dictionary(dict) => f.debug_tuple("Dictionary").field(dict).finish(),
        }
    }
}

impl fmt::Debug for own::List {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(f)
    }
}

impl fmt::Debug for own::Dictionary {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_map()
            .entries(self.0.iter().map(|(k, v)| (EscapeAscii(k), v)))
            .finish()
    }
}

impl<'a> fmt::Debug for borrow::List<'a> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.list.fmt(f)
    }
}

impl<'a> fmt::Debug for borrow::Dictionary<'a> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_map()
            .entries(self.dict.iter().map(|(k, v)| (EscapeAscii(k), v)))
            .finish()
    }
}

pub struct FormatDictionary<'a>(pub &'a BTreeMap<&'a [u8], borrow::Value<'a>>);

impl<'a> fmt::Debug for FormatDictionary<'a> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_map()
            .entries(self.0.iter().map(|(k, v)| (EscapeAscii(k), v)))
            .finish()
    }
}

impl From<own::ByteString> for own::Value {
    fn from(bytes: own::ByteString) -> Self {
        Self::ByteString(bytes)
    }
}

impl From<i64> for own::Value {
    fn from(int: i64) -> Self {
        Self::Integer(int)
    }
}

impl From<Vec<own::Value>> for own::Value {
    fn from(list: Vec<own::Value>) -> Self {
        Self::List(own::List(list))
    }
}

impl From<BTreeMap<own::ByteString, own::Value>> for own::Value {
    fn from(dict: BTreeMap<own::ByteString, own::Value>) -> Self {
        Self::Dictionary(own::Dictionary(dict))
    }
}

// `borrow::ValueOwner::try_from` requires this.
impl<'a> TryFrom<&'a [u8]> for borrow::Value<'a> {
    type Error = Error;

    fn try_from(mut buffer: &'a [u8]) -> Result<Self, Self::Error> {
        let value = Self::decode(&mut buffer)?;
        ensure!(
            !buffer.has_remaining(),
            UnexpectedTrailingDataSnafu {
                value: value.to_owned(),
                trailing_data: buffer.escape_ascii().to_string(),
            },
        );
        Ok(value)
    }
}

impl<'a, ByteString, List, Dictionary> Value<ByteString, List, Dictionary>
where
    Self: private::ValueNew<'a, ByteString, List, Dictionary> + 'a,
    ByteString: AsRef<[u8]> + Ord + 'a,
    List: 'a,
    Dictionary: 'a,
{
    pub fn decode<Buffer>(buffer: &mut Buffer) -> Result<Self, Error>
    where
        Buffer: BufPeekExt + BufSliceExt + 'a,
    {
        use private::ValueNew;

        match buffer.peek_u8().ok_or(Error::Incomplete)? {
            b'0'..=b'9' => Ok(Self::ByteString(Self::new_byte_string(decode_byte_string(
                buffer,
            )?))),
            b'i' => {
                buffer.advance(1);
                let int = buffer
                    .get_slice_until_strip(|x| *x == b'e')
                    .ok_or(Error::Incomplete)?;
                Ok(Self::Integer(decode_integer(int).ok_or_else(|| {
                    Error::InvalidInteger {
                        integer: int.escape_ascii().to_string(),
                    }
                })?))
            }
            b'l' => {
                let mut list = Vec::new();
                let mut buf = buffer.dup();
                buf.advance(1);
                while buf.peek_u8().ok_or(Error::Incomplete)? != b'e' {
                    list.push(Self::decode(&mut buf)?);
                }
                buf.advance(1);
                Ok(Self::List(Self::new_list(
                    list,
                    buffer.get_slice(buffer.remaining() - buf.remaining()),
                )))
            }
            b'd' => {
                let mut dict = BTreeMap::<ByteString, Self>::new();
                let mut buf = buffer.dup();
                buf.advance(1);
                while buf.peek_u8().ok_or(Error::Incomplete)? != b'e' {
                    let key = Self::new_byte_string(decode_byte_string(&mut buf)?);
                    let value = Self::decode(&mut buf)?;
                    if let Some((last_key, _)) = dict.last_key_value() {
                        ensure!(
                            *last_key < key,
                            NotStrictlyIncreasingDictionaryKeySnafu {
                                last_key: last_key.as_ref().escape_ascii().to_string(),
                                new_key: key.as_ref().escape_ascii().to_string(),
                            },
                        );
                    }
                    dict.insert(key, value);
                }
                buf.advance(1);
                Ok(Self::Dictionary(Self::new_dictionary(
                    dict,
                    buffer.get_slice(buffer.remaining() - buf.remaining()),
                )))
            }
            value_type => Err(Error::InvalidValueType { value_type }),
        }
    }
}

fn decode_byte_string<'a, Buffer>(buffer: &mut Buffer) -> Result<&'a [u8], Error>
where
    Buffer: BufPeekExt + BufSliceExt + 'a,
{
    let length = buffer
        .get_slice_until_strip(|x| *x == b':')
        .ok_or(Error::Incomplete)?;
    let length = decode_integer(length).ok_or_else(|| Error::InvalidByteStringLength {
        length: length.escape_ascii().to_string(),
    })?;
    buffer.try_get_slice(length).ok_or(Error::Incomplete)
}

/// Decodes an integer from a slice.
///
/// TODO: Currently, it can decode any type that implements `FromStr`.  We need to restrict it to
/// accept only integer types.
fn decode_integer<T>(int: &[u8]) -> Option<T>
where
    T: FromStr,
{
    str::from_utf8(int)
        .ok()
        .and_then(|int| int.parse::<T>().ok())
}

impl<ByteString, List, Dictionary> Value<ByteString, List, Dictionary>
where
    ByteString: AsRef<[u8]>,
    List: Deref<Target = Vec<Self>>,
    Dictionary: Deref<Target = BTreeMap<ByteString, Self>>,
{
    pub fn encode<Buffer>(&self, buffer: &mut Buffer)
    where
        Buffer: BufMut,
    {
        match self {
            Self::ByteString(bytes) => Self::encode_byte_string(bytes, buffer),
            Self::Integer(int) => {
                buffer.put_u8(b'i');
                buffer.put_display(int).unwrap();
                buffer.put_u8(b'e');
            }
            Self::List(list) => {
                buffer.put_u8(b'l');
                list.iter().for_each(|item| item.encode(buffer));
                buffer.put_u8(b'e');
            }
            Self::Dictionary(dict) => {
                buffer.put_u8(b'd');
                dict.iter().for_each(|(key, value)| {
                    Self::encode_byte_string(key, buffer);
                    value.encode(buffer);
                });
                buffer.put_u8(b'e');
            }
        }
    }

    fn encode_byte_string<Buffer>(bytes: &ByteString, buffer: &mut Buffer)
    where
        Buffer: BufMut,
    {
        let slice = bytes.as_ref();
        buffer.put_display(&slice.len()).unwrap();
        buffer.put_u8(b':');
        buffer.put_slice(slice);
    }
}

impl<ByteString, List, Dictionary> Value<ByteString, List, Dictionary>
where
    List: Deref<Target = Vec<Self>>,
    Dictionary: Deref<Target = BTreeMap<ByteString, Self>>,
{
    pub fn as_byte_string(&self) -> Option<&ByteString> {
        match self {
            Value::ByteString(bytes) => Some(bytes),
            _ => None,
        }
    }

    pub fn as_integer(&self) -> Option<i64> {
        match self {
            Value::Integer(int) => Some(*int),
            _ => None,
        }
    }

    pub fn as_list(&self) -> Option<&Vec<Self>> {
        match self {
            Value::List(list) => Some(&**list),
            _ => None,
        }
    }

    pub fn as_dictionary(&self) -> Option<&BTreeMap<ByteString, Self>> {
        match self {
            Value::Dictionary(dict) => Some(&**dict),
            _ => None,
        }
    }
}

impl<'a, ByteString, List, Dictionary> Value<ByteString, List, Dictionary>
where
    Self: private::ValueInto<'a, ByteString> + 'a,
    ByteString: 'a,
{
    pub fn into_byte_string(self) -> Result<ByteString, Self> {
        match self {
            Value::ByteString(bytes) => Ok(bytes),
            _ => Err(self),
        }
    }

    pub fn into_integer(self) -> Result<i64, Self> {
        match self {
            Value::Integer(int) => Ok(int),
            _ => Err(self),
        }
    }

    pub fn into_list(self) -> Result<(Vec<Self>, Option<&'a [u8]>), Self> {
        private::ValueInto::<'a, ByteString>::into_list(self)
    }

    #[allow(clippy::type_complexity)]
    pub fn into_dictionary(self) -> Result<(BTreeMap<ByteString, Self>, Option<&'a [u8]>), Self> {
        private::ValueInto::<'a, ByteString>::into_dictionary(self)
    }
}

impl<'a> borrow::Value<'a> {
    pub fn new_list_without_raw_value(list: Vec<borrow::Value<'a>>) -> Self {
        Self::List(borrow::List {
            list,
            raw_value: b"",
        })
    }

    pub fn new_dictionary_without_raw_value(
        dict: BTreeMap<borrow::ByteString<'a>, borrow::Value<'a>>,
    ) -> Self {
        Self::Dictionary(borrow::Dictionary {
            dict,
            raw_value: b"",
        })
    }

    pub fn raw_value(&self) -> &'a [u8] {
        match self {
            Self::List(list) => list.raw_value,
            Self::Dictionary(dict) => dict.raw_value,
            Self::ByteString(_) | Self::Integer(_) => {
                panic!("we do not store raw value for these types: {:?}", self)
            }
        }
    }

    /// Converts from `borrow::Value` to `own::Value`.
    ///
    /// This method that is similar to `std::borrow::ToOwned`.  However we cannot implement
    /// `std::borrow::ToOwned` for `borrow::Value` because `own::Value` does not implement
    /// `Borrow<borrow::Value>`.
    pub fn to_owned(&self) -> own::Value {
        match self {
            Self::ByteString(bytes) => own::ByteString::from(*bytes).into(),
            Self::Integer(int) => (*int).into(),
            Self::List(borrow::List { list, .. }) => {
                list.iter().map(Self::to_owned).collect::<Vec<_>>().into()
            }
            Self::Dictionary(borrow::Dictionary { dict, .. }) => dict
                .iter()
                .map(|(key, value)| ((*key).into(), value.to_owned()))
                .collect::<BTreeMap<_, _>>()
                .into(),
        }
    }
}

mod private {
    use std::collections::BTreeMap;

    use super::{borrow, own};

    pub trait ValueNew<'a, ByteString, List, Dictionary>
    where
        Self: Sized + 'a,
        ByteString: 'a,
        List: 'a,
        Dictionary: 'a,
    {
        fn new_byte_string(bytes: &'a [u8]) -> ByteString;

        fn new_list(list: Vec<Self>, raw_value: &'a [u8]) -> List;

        fn new_dictionary(dict: BTreeMap<ByteString, Self>, raw_value: &'a [u8]) -> Dictionary;
    }

    impl<'a> ValueNew<'a, own::ByteString, own::List, own::Dictionary> for own::Value {
        fn new_byte_string(bytes: &'a [u8]) -> own::ByteString {
            bytes.into()
        }

        fn new_list(list: Vec<Self>, _: &'a [u8]) -> own::List {
            own::List(list)
        }

        fn new_dictionary(dict: BTreeMap<own::ByteString, Self>, _: &'a [u8]) -> own::Dictionary {
            own::Dictionary(dict)
        }
    }

    impl<'a> ValueNew<'a, borrow::ByteString<'a>, borrow::List<'a>, borrow::Dictionary<'a>>
        for borrow::Value<'a>
    {
        fn new_byte_string(bytes: &'a [u8]) -> borrow::ByteString<'a> {
            bytes
        }

        fn new_list(list: Vec<Self>, raw_value: &'a [u8]) -> borrow::List<'a> {
            borrow::List { list, raw_value }
        }

        fn new_dictionary(
            dict: BTreeMap<borrow::ByteString<'a>, Self>,
            raw_value: &'a [u8],
        ) -> borrow::Dictionary<'a> {
            borrow::Dictionary { dict, raw_value }
        }
    }

    pub trait ValueInto<'a, ByteString>
    where
        Self: Sized + 'a,
        ByteString: 'a,
    {
        fn into_list(self) -> Result<(Vec<Self>, Option<&'a [u8]>), Self>;

        #[allow(clippy::type_complexity)]
        fn into_dictionary(self) -> Result<(BTreeMap<ByteString, Self>, Option<&'a [u8]>), Self>;
    }

    impl<'a> ValueInto<'a, own::ByteString> for own::Value {
        fn into_list(self) -> Result<(Vec<Self>, Option<&'a [u8]>), Self> {
            match self {
                own::Value::List(list) => Ok((list.0, None)),
                _ => Err(self),
            }
        }

        fn into_dictionary(
            self,
        ) -> Result<(BTreeMap<own::ByteString, Self>, Option<&'a [u8]>), Self> {
            match self {
                own::Value::Dictionary(dict) => Ok((dict.0, None)),
                _ => Err(self),
            }
        }
    }

    impl<'a> ValueInto<'a, borrow::ByteString<'a>> for borrow::Value<'a> {
        fn into_list(self) -> Result<(Vec<Self>, Option<&'a [u8]>), Self> {
            match self {
                borrow::Value::List(list) => Ok((list.list, Some(list.raw_value))),
                _ => Err(self),
            }
        }

        fn into_dictionary(
            self,
        ) -> Result<(BTreeMap<borrow::ByteString<'a>, Self>, Option<&'a [u8]>), Self> {
            match self {
                borrow::Value::Dictionary(dict) => Ok((dict.dict, Some(dict.raw_value))),
                _ => Err(self),
            }
        }
    }
}

#[cfg(any(test, feature = "test_harness"))]
mod test_harness {
    use super::*;

    // We implement `From` for `borrow::Value` only during testing to allow unit tests to construct
    // borrowed values.  Note that the constructed list and dictionary values do not have the raw
    // Bencode data.
    //
    // We cannot implement `From<&[u8]>` for `borrow::Value` because it conflicts with the
    // `TryFrom<&[u8]>` implementation above.
    impl<'a> borrow::Value<'a> {
        pub fn new_byte_string(bytes: &[u8]) -> borrow::Value<'_> {
            borrow::Value::ByteString(bytes)
        }
    }

    impl<'a> From<i64> for borrow::Value<'a> {
        fn from(int: i64) -> Self {
            Self::Integer(int)
        }
    }

    impl<'a> From<Vec<borrow::Value<'a>>> for borrow::Value<'a> {
        fn from(list: Vec<borrow::Value<'a>>) -> Self {
            Self::new_list_without_raw_value(list)
        }
    }

    impl<'a> From<BTreeMap<borrow::ByteString<'a>, borrow::Value<'a>>> for borrow::Value<'a> {
        fn from(dict: BTreeMap<borrow::ByteString<'a>, borrow::Value<'a>>) -> Self {
            Self::new_dictionary_without_raw_value(dict)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn new_owned_bytes(bytes: &[u8]) -> own::ByteString {
        own::ByteString::from(bytes)
    }

    #[test]
    fn decode_ok() {
        fn test(data: &[u8], expect: borrow::Value) {
            let mut buffer = data;
            let value = borrow::Value::decode(&mut buffer).unwrap();
            assert_eq!(value, expect);
            assert_eq!(buffer, b"");

            let mut buffer = Vec::new();
            value.encode(&mut buffer);
            assert_eq!(&buffer, data);

            if matches!(value, borrow::Value::List(_) | borrow::Value::Dictionary(_)) {
                assert_eq!(value.raw_value(), data);
            }
        }

        test(b"0:", borrow::Value::new_byte_string(b""));
        test(b"1:\t", borrow::Value::new_byte_string(b"\t"));
        test(
            b"11:hello world",
            borrow::Value::new_byte_string(b"hello world"),
        );

        test(b"i0e", 0.into());
        test(b"i-1e", (-1).into());
        test(b"i42e", 42.into());

        test(b"le", vec![].into());
        test(
            b"llelleee",
            vec![vec![].into(), vec![vec![].into()].into()].into(),
        );
        test(
            b"li0e0:li1e1:xee",
            vec![
                0.into(),
                borrow::Value::new_byte_string(b""),
                vec![1.into(), borrow::Value::new_byte_string(b"x")].into(),
            ]
            .into(),
        );

        test(b"de", BTreeMap::new().into());
        test(
            b"d1:ad2:aad3:aaadeeee",
            BTreeMap::from([(
                b"a".as_slice(),
                BTreeMap::from([(
                    b"aa".as_slice(),
                    BTreeMap::from([(b"aaa".as_slice(), BTreeMap::new().into())]).into(),
                )])
                .into(),
            )])
            .into(),
        );
        test(
            b"d0:0:1:a1:x1:bi-101e1:cle1:ddee",
            BTreeMap::from([
                (b"".as_slice(), borrow::Value::new_byte_string(b"")),
                (b"a".as_slice(), borrow::Value::new_byte_string(b"x")),
                (b"b".as_slice(), (-101).into()),
                (b"c".as_slice(), vec![].into()),
                (b"d".as_slice(), BTreeMap::new().into()),
            ])
            .into(),
        );
    }

    #[test]
    fn decode_err() {
        fn test(mut buffer: &[u8], error: Error) {
            assert_eq!(borrow::Value::decode(&mut buffer), Err(error));
        }

        test(b"", Error::Incomplete);
        test(b"0", Error::Incomplete);
        test(b"1:", Error::Incomplete);
        test(b"i", Error::Incomplete);
        test(b"i1", Error::Incomplete);
        test(b"l", Error::Incomplete);
        test(b"lllee", Error::Incomplete);
        test(b"d", Error::Incomplete);
        test(b"d1:a1:b", Error::Incomplete);
        test(b"ddd", Error::Incomplete);

        test(
            b"0x01:",
            Error::InvalidByteStringLength {
                length: "0x01".to_string(),
            },
        );

        test(
            b"ie",
            Error::InvalidInteger {
                integer: "".to_string(),
            },
        );
        test(
            b"i0x01e",
            Error::InvalidInteger {
                integer: "0x01".to_string(),
            },
        );

        test(
            b"d1:ble1:alee",
            Error::NotStrictlyIncreasingDictionaryKey {
                last_key: "b".to_string(),
                new_key: "a".to_string(),
            },
        );
        test(
            b"d1:ale1:alee",
            Error::NotStrictlyIncreasingDictionaryKey {
                last_key: "a".to_string(),
                new_key: "a".to_string(),
            },
        );

        test(b"x", Error::InvalidValueType { value_type: b'x' });

        assert_eq!(
            borrow::Value::try_from(b"defoobar".as_slice()),
            Err(Error::UnexpectedTrailingData {
                value: BTreeMap::new().into(),
                trailing_data: "foobar".to_string(),
            }),
        );
    }

    #[test]
    fn own_value() {
        fn test(data: &[u8], expect: own::Value) {
            let mut buffer = data;
            let value = own::Value::decode(&mut buffer).unwrap();
            assert_eq!(value, expect);
            assert_eq!(buffer, b"");

            let mut buffer = Vec::new();
            value.encode(&mut buffer);
            assert_eq!(&buffer, data);
        }

        test(b"3:foo", new_owned_bytes(b"foo").into());
        test(b"i-1234e", (-1234).into());
        test(
            b"li42e6:foobare",
            vec![own::Value::from(42), new_owned_bytes(b"foobar").into()].into(),
        );
        test(b"de", BTreeMap::new().into());
        test(
            b"d4:spam3:egge",
            BTreeMap::from([(b"spam".as_slice().into(), new_owned_bytes(b"egg").into())]).into(),
        );
    }

    #[test]
    fn raw_value() {
        fn as_list<'a>(value: &'a borrow::Value<'a>) -> &'a borrow::List<'a> {
            match value {
                borrow::Value::List(list) => list,
                _ => panic!("expect list: {:?}", value),
            }
        }

        fn as_dict<'a>(value: &'a borrow::Value<'a>) -> &'a borrow::Dictionary<'a> {
            match value {
                borrow::Value::Dictionary(dict) => dict,
                _ => panic!("expect dictionary: {:?}", value),
            }
        }

        let value = borrow::Value::try_from(b"llelleee".as_slice()).unwrap();
        assert_eq!(value.raw_value(), b"llelleee");
        let list = as_list(&value);
        assert_eq!(list[0].raw_value(), b"le");
        assert_eq!(list[1].raw_value(), b"llee");
        let list = as_list(&list[1]);
        assert_eq!(list[0].raw_value(), b"le");

        let value = borrow::Value::try_from(b"d1:ad1:bd1:cdeeee".as_slice()).unwrap();
        assert_eq!(value.raw_value(), b"d1:ad1:bd1:cdeeee");
        let dict = &as_dict(&value)[b"a".as_slice()];
        assert_eq!(dict.raw_value(), b"d1:bd1:cdeee");
        let dict = &as_dict(dict)[b"b".as_slice()];
        assert_eq!(dict.raw_value(), b"d1:cdee");
        let dict = &as_dict(dict)[b"c".as_slice()];
        assert_eq!(dict.raw_value(), b"de");
    }

    #[test]
    fn value_as() {
        let value = own::Value::from(new_owned_bytes(b"foo"));
        assert_eq!(value.as_byte_string(), Some(&new_owned_bytes(b"foo")));
        assert_eq!(value.as_integer(), None);
        assert_eq!(value.as_list(), None);
        assert_eq!(value.as_dictionary(), None);

        let value = own::Value::from(42);
        assert_eq!(value.as_byte_string(), None);
        assert_eq!(value.as_integer(), Some(42));
        assert_eq!(value.as_list(), None);
        assert_eq!(value.as_dictionary(), None);

        let value = own::Value::from(vec![]);
        assert_eq!(value.as_byte_string(), None);
        assert_eq!(value.as_integer(), None);
        assert_eq!(value.as_list(), Some(&vec![]));
        assert_eq!(value.as_dictionary(), None);

        let value = own::Value::from(BTreeMap::new());
        assert_eq!(value.as_byte_string(), None);
        assert_eq!(value.as_integer(), None);
        assert_eq!(value.as_list(), None);
        assert_eq!(value.as_dictionary(), Some(&BTreeMap::new()));

        let value = borrow::Value::new_byte_string(b"foo");
        assert_eq!(value.as_byte_string(), Some(&b"foo".as_slice()));
        assert_eq!(value.as_integer(), None);
        assert_eq!(value.as_list(), None);
        assert_eq!(value.as_dictionary(), None);

        let value = borrow::Value::from(42);
        assert_eq!(value.as_byte_string(), None);
        assert_eq!(value.as_integer(), Some(42));
        assert_eq!(value.as_list(), None);
        assert_eq!(value.as_dictionary(), None);

        let value = borrow::Value::from(vec![]);
        assert_eq!(value.as_byte_string(), None);
        assert_eq!(value.as_integer(), None);
        assert_eq!(value.as_list(), Some(&vec![]));
        assert_eq!(value.as_dictionary(), None);

        let value = borrow::Value::from(BTreeMap::new());
        assert_eq!(value.as_byte_string(), None);
        assert_eq!(value.as_integer(), None);
        assert_eq!(value.as_list(), None);
        assert_eq!(value.as_dictionary(), Some(&BTreeMap::new()));
    }

    #[test]
    fn value_into() {
        let value = own::Value::from(new_owned_bytes(b"foo"));
        assert_eq!(
            value.clone().into_byte_string(),
            Ok(new_owned_bytes(b"foo")),
        );
        assert_eq!(value.clone().into_integer(), Err(value.clone()));
        assert_eq!(value.clone().into_list(), Err(value.clone()));
        assert_eq!(value.clone().into_dictionary(), Err(value.clone()));

        let value = own::Value::from(42);
        assert_eq!(value.clone().into_byte_string(), Err(value.clone()));
        assert_eq!(value.clone().into_integer(), Ok(42));
        assert_eq!(value.clone().into_list(), Err(value.clone()));
        assert_eq!(value.clone().into_dictionary(), Err(value.clone()));

        let value = own::Value::from(vec![]);
        assert_eq!(value.clone().into_byte_string(), Err(value.clone()));
        assert_eq!(value.clone().into_integer(), Err(value.clone()));
        assert_eq!(value.clone().into_list(), Ok((vec![], None)));
        assert_eq!(value.clone().into_dictionary(), Err(value.clone()));

        let value = own::Value::from(BTreeMap::new());
        assert_eq!(value.clone().into_byte_string(), Err(value.clone()));
        assert_eq!(value.clone().into_integer(), Err(value.clone()));
        assert_eq!(value.clone().into_list(), Err(value.clone()));
        assert_eq!(value.clone().into_dictionary(), Ok((BTreeMap::new(), None)));

        let value = borrow::Value::new_byte_string(b"foo");
        assert_eq!(value.clone().into_byte_string(), Ok(b"foo".as_slice()));
        assert_eq!(value.clone().into_integer(), Err(value.clone()));
        assert_eq!(value.clone().into_list(), Err(value.clone()));
        assert_eq!(value.clone().into_dictionary(), Err(value.clone()));

        let value = borrow::Value::from(42);
        assert_eq!(value.clone().into_byte_string(), Err(value.clone()));
        assert_eq!(value.clone().into_integer(), Ok(42));
        assert_eq!(value.clone().into_list(), Err(value.clone()));
        assert_eq!(value.clone().into_dictionary(), Err(value.clone()));

        let value = borrow::Value::from(vec![]);
        assert_eq!(value.clone().into_byte_string(), Err(value.clone()));
        assert_eq!(value.clone().into_integer(), Err(value.clone()));
        assert_eq!(
            value.clone().into_list(),
            Ok((vec![], Some(b"".as_slice()))),
        );
        assert_eq!(value.clone().into_dictionary(), Err(value.clone()));

        let value = borrow::Value::from(BTreeMap::new());
        assert_eq!(value.clone().into_byte_string(), Err(value.clone()));
        assert_eq!(value.clone().into_integer(), Err(value.clone()));
        assert_eq!(value.clone().into_list(), Err(value.clone()));
        assert_eq!(
            value.clone().into_dictionary(),
            Ok((BTreeMap::new(), Some(b"".as_slice()))),
        );
    }
}
