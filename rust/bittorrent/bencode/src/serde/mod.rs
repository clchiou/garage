mod de;
mod error;
mod ser;

pub use de::{from_bytes, Deserializer};
pub use error::{Error, Result};
pub use ser::{to_bytes, Serializer};

/// Converts from one integer type to another.
///
/// TODO: Currently, it can convert any type that implements `TryFrom`.  We need to restrict it to
/// accept only integer types.
fn to_int<T, U>(x: T) -> Result<U>
where
    U: TryFrom<T>,
{
    U::try_from(x).map_err(|_| Error::IntegerValueOutOfRange)
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;
    use std::fmt;

    use bytes::BytesMut;
    use serde::{Deserialize, Serialize};

    use super::*;

    #[derive(Debug, Deserialize, Eq, PartialEq, Serialize)]
    struct Unit;

    #[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
    struct Struct<'a> {
        int: u32,
        list: Vec<&'a str>,
        #[serde(with = "serde_bytes")]
        bytes: &'a [u8],
    }

    #[derive(Debug, Deserialize, Eq, PartialEq, Serialize)]
    struct Newtype<'a>(#[serde(borrow)] Struct<'a>);

    #[derive(Debug, Deserialize, Eq, PartialEq, Serialize)]
    enum Enum<'a> {
        Unit,
        #[serde(borrow)]
        Newtype(Struct<'a>),
        Tuple(u32, u32),
        Struct {
            x: u32,
        },
    }

    #[test]
    fn test_ok() {
        fn test<'a, T>(value: T, expect: &'a [u8])
        where
            T: fmt::Debug + PartialEq + Deserialize<'a> + Serialize,
        {
            assert_eq!(to_bytes(&value), Ok(BytesMut::from(expect)));
            assert_eq!(from_bytes::<T>(expect), Ok(value));
        }

        test(false, b"i0e");
        test(true, b"i1e");
        test(42u8, b"i42e");
        test(-1i32, b"i-1e");
        test(0.1f32, b"4:\x3d\xcc\xcc\xcd");
        test(0.1f64, b"8:\x3f\xb9\x99\x99\x99\x99\x99\x9a");
        test('A', b"i65e");
        test("hello world\n", b"12:hello world\n");
        test(None::<u8>, b"le");
        test(Some(1), b"li1ee");
        test((), b"le");
        test(Unit, b"le");
        test(vec![vec![0u8]], b"lli0eee");
        test((1, "foo"), b"li1e3:fooe");
        test(BTreeMap::from([("foo", "bar")]), b"d3:foo3:bare");

        let value = Struct {
            int: 42,
            list: vec!["foo", "bar"],
            bytes: b"hello world\n",
        };
        let struct_expect = b"d5:bytes12:hello world\n3:inti42e4:listl3:foo3:baree";
        test(value.clone(), struct_expect);
        test(Newtype(value.clone()), struct_expect);

        let mut enum_expect = b"d7:Newtype".to_vec();
        enum_expect.extend(struct_expect);
        enum_expect.push(b'e');
        test(Enum::Unit, b"4:Unit");
        test(Enum::Newtype(value), &enum_expect);
        test(Enum::Tuple(1, 2), b"d5:Tupleli1ei2eee");
        test(Enum::Struct { x: 3 }, b"d6:Structd1:xi3eee");
    }

    #[test]
    fn test_err() {
        assert_eq!(
            from_bytes::<()>(b""),
            Err(Error::Decode {
                source: crate::Error::Incomplete,
            }),
        );
        assert_eq!(
            from_bytes::<u8>(b"le"),
            Err(Error::ExpectValueType {
                type_name: "Integer",
                value: vec![].into(),
            }),
        );
        assert_eq!(
            from_bytes::<u8>(b"i256e"),
            Err(Error::IntegerValueOutOfRange),
        );
        assert_eq!(
            from_bytes::<Enum>(b"de"),
            Err(Error::InvalidDictionaryAsEnum {
                dict: BTreeMap::new().into(),
            }),
        );
        assert_eq!(
            from_bytes::<f32>(b"0:"),
            Err(Error::InvalidFloatingPoint { value: vec![] }),
        );
        assert_eq!(
            from_bytes::<()>(b"li0ee"),
            Err(Error::InvalidListAsType {
                type_name: "unit",
                list: vec![0.into()].into(),
            }),
        );
        assert_eq!(
            from_bytes::<String>(b"2:\xc3\x28"),
            Err(Error::InvalidUtf8String {
                string: b"\xc3\x28".escape_ascii().to_string(),
            }),
        );

        assert_eq!(
            to_bytes(&BTreeMap::from([(0u8, 0u8)])),
            Err(Error::ExpectValueType {
                type_name: "ByteString",
                value: 0.into(),
            }),
        );
        assert_eq!(to_bytes(&u64::MAX), Err(Error::IntegerValueOutOfRange));
    }
}
