mod de;
mod error;
mod ser;

pub use de::{Deserializer, from_bytes, from_bytes_lenient, from_bytes_lenient_two_pass};
pub use error::{Error, Result};
pub use ser::{Serializer, to_bytes};

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
    use std::assert_matches::assert_matches;
    use std::collections::BTreeMap;
    use std::fmt;

    use bytes::BytesMut;
    use serde::{Deserialize, Serialize};
    use serde_bytes::Bytes;

    use crate::{borrow, own};

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

    #[derive(Debug, Deserialize, Eq, PartialEq, Serialize)]
    struct ValueField<'a> {
        #[serde(borrow)]
        field: borrow::Value<'a>,
    }

    #[derive(Debug, Deserialize, Eq, PartialEq, Serialize)]
    struct Flatten<'a> {
        #[serde(borrow, flatten)]
        map: BTreeMap<&'a Bytes, own::Value>,
    }

    #[test]
    fn test_ok() {
        fn test<'a, T>(value: T, expect: &'a [u8])
        where
            T: fmt::Debug + PartialEq + Deserialize<'a> + Serialize,
        {
            assert_eq!(to_bytes(&value), Ok(BytesMut::from(expect)));
            assert_eq!(from_bytes::<T>(expect), Ok(value));

            let borrowed_value = borrow::Value::try_from(expect).unwrap();
            let owned_value = borrowed_value.to_owned();

            let value = own::Value::deserialize(Deserializer::from_bytes(expect));
            assert_eq!(value, Ok(owned_value.clone()));
            let value = borrow::Value::deserialize(Deserializer::from_bytes(expect));
            assert_eq!(value, Ok(borrowed_value.clone()));
            let value = value.unwrap();
            if matches!(value, borrow::Value::List(_) | borrow::Value::Dictionary(_)) {
                assert_eq!(value.raw_value(), expect);
            }

            assert_eq!(owned_value.serialize(Serializer), Ok(owned_value.clone()));
            assert_eq!(borrowed_value.serialize(Serializer), Ok(owned_value));
        }

        test(false, b"i0e");
        test(true, b"i1e");
        test(42u8, b"i42e");
        test(-1i32, b"i-1e");
        test(0.1f32, b"4:\x3d\xcc\xcc\xcd");
        test(0.1f64, b"8:\x3f\xb9\x99\x99\x99\x99\x99\x9a");
        test('A', b"i65e");
        test("hello world\n", b"12:hello world\n");
        test(Bytes::new(b"hello world\n"), b"12:hello world\n");
        test(None::<u8>, b"le");
        test(Some(1), b"li1ee");
        test((), b"le");
        test(Unit, b"le");
        test(vec![vec![0u8]], b"lli0eee");
        test(vec!["foo"], b"l3:fooe");
        test(vec![Bytes::new(b"bar")], b"l3:bare");
        test((1, "foo", Bytes::new(b"bar")), b"li1e3:foo3:bare");
        test(BTreeMap::from([("foo", "bar")]), b"d3:foo3:bare");
        test(
            BTreeMap::from([(Bytes::new(b"foo"), Bytes::new(b"bar"))]),
            b"d3:foo3:bare",
        );

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

        let value = ValueField {
            field: BTreeMap::from([(
                b"a".as_slice(),
                BTreeMap::from([(
                    b"b".as_slice(),
                    BTreeMap::from([(b"c".as_slice(), BTreeMap::new().into())]).into(),
                )])
                .into(),
            )])
            .into(),
        };
        test(value, b"d5:fieldd1:ad1:bd1:cdeeeee");

        let value = Flatten {
            map: BTreeMap::from([(
                Bytes::new(b"a"),
                BTreeMap::from([(
                    own::ByteString::from(b"b".as_slice()).into(),
                    BTreeMap::from([(
                        own::ByteString::from(b"c".as_slice()).into(),
                        BTreeMap::new().into(),
                    )])
                    .into(),
                )])
                .into(),
            )]),
        };
        test(value, b"d1:ad1:bd1:cdeeee");
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

    #[test]
    fn raw_value() {
        fn as_list<'a>(value: &'a borrow::Value<'a>) -> &'a borrow::List<'a, true> {
            match value {
                borrow::Value::List(list) => list,
                _ => panic!("expect list: {:?}", value),
            }
        }

        fn as_dict<'a>(value: &'a borrow::Value<'a>) -> &'a borrow::Dictionary<'a, true> {
            match value {
                borrow::Value::Dictionary(dict) => dict,
                _ => panic!("expect dictionary: {:?}", value),
            }
        }

        let value = borrow::Value::deserialize(Deserializer::from_bytes(b"llelleee")).unwrap();
        assert_eq!(value.raw_value(), b"llelleee");
        let list = as_list(&value);
        assert_eq!(list[0].raw_value(), b"le");
        assert_eq!(list[1].raw_value(), b"llee");
        let list = as_list(&list[1]);
        assert_eq!(list[0].raw_value(), b"le");

        let value =
            borrow::Value::deserialize(Deserializer::from_bytes(b"d1:ad1:bd1:cdeeee")).unwrap();
        assert_eq!(value.raw_value(), b"d1:ad1:bd1:cdeeee");
        let dict = &as_dict(&value)[b"a".as_slice()];
        assert_eq!(dict.raw_value(), b"d1:bd1:cdeee");
        let dict = &as_dict(dict)[b"b".as_slice()];
        assert_eq!(dict.raw_value(), b"d1:cdee");
        let dict = &as_dict(dict)[b"c".as_slice()];
        assert_eq!(dict.raw_value(), b"de");
    }

    #[test]
    fn lenient() {
        fn test(data: &[u8], expect: borrow::Value) {
            assert_matches!(
                from_bytes::<borrow::Value>(data),
                Err(Error::Decode {
                    source: crate::Error::NotStrictlyIncreasingDictionaryKey { .. },
                }),
            );

            // Wrong combinations.
            assert_matches!(
                from_bytes::<borrow::Value<false>>(data),
                Err(Error::Decode {
                    source: crate::Error::NotStrictlyIncreasingDictionaryKey { .. },
                }),
            );
            assert_matches!(
                from_bytes_lenient::<borrow::Value>(data),
                Err(Error::Custom { .. }),
            );

            let value = from_bytes_lenient::<borrow::Value<false>>(data).unwrap();
            assert_eq!(value.to_strict(), expect);
        }

        let expect = borrow::Value::from(BTreeMap::from([(
            b"a".as_slice(),
            borrow::Value::new_byte_string(b"c"),
        )]));
        test(b"d1:a1:b1:a1:ce", expect.clone());
        test(
            b"d1:ad1:ad1:a1:b1:a1:ceee",
            BTreeMap::from([(
                b"a".as_slice(),
                BTreeMap::from([(b"a".as_slice(), expect.clone())]).into(),
            )])
            .into(),
        );
        test(b"lld1:a1:b1:a1:ceee", vec![vec![expect].into()].into());

        let data = b"i42ehello world".as_slice();
        assert_matches!(
            from_bytes::<u8>(data),
            Err(Error::Decode {
                source: crate::Error::UnexpectedTrailingData { .. },
            }),
        );
        assert_eq!(from_bytes_lenient::<u8>(data), Ok(42));
    }
}
