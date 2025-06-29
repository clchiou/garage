use serde::ser::{Serialize, Serializer};
use serde_bytes::Bytes;

use super::{MAGIC, WithRaw};

impl<T, D> Serialize for WithRaw<T, D>
where
    T: Serialize,
    D: AsRef<[u8]>,
{
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_newtype_struct(MAGIC, &(&self.0, Bytes::new(self.1.as_ref())))
    }
}

#[cfg(test)]
mod tests {
    use bytes::Bytes;

    use crate::ser;
    use crate::testing::{NestedA, NestedB, NestedC, StrictStruct, Tuple, vb, vd, vi, vl};
    use crate::value::{self, Value};

    use super::*;

    #[test]
    fn serialize_to_value() {
        fn test<T>(value: T, expect: Value<&[u8]>)
        where
            T: Serialize,
        {
            assert_eq!(
                value::ser::to_value(&WithRaw(value, b"".as_slice())),
                Ok(expect.to_own::<Bytes>()),
            );
        }

        test("hello world", vb(b"hello world"));
        test(42u8, vi(42));
        test(Tuple(1, "foo".to_string()), vl([vi(1), vb(b"foo")]));
        test(StrictStruct { x: 2 }, vd([(b"x", vi(2))]));

        test(WithRaw(42u8, b"".as_slice()), vi(42));
    }

    #[test]
    fn serialize_to_bytes() {
        assert_eq!(
            ser::to_bytes(&WithRaw((), b"foobar".as_slice())),
            Ok(Bytes::from_static(b"foobar")),
        );
    }

    #[test]
    fn nested() {
        let value = NestedA {
            a: "value a".to_string(),
            nested: WithRaw(
                NestedB {
                    b: "value b".to_string(),
                    nested: WithRaw(
                        NestedC {
                            c: "value c".to_string(),
                            nested: WithRaw("value d".to_string(), Bytes::from_static(b"spam")),
                        },
                        Bytes::from_static(b"egg"),
                    ),
                },
                Bytes::from_static(b"foobar"),
            ),
        };

        assert_eq!(
            value::ser::to_value(&value),
            Ok(vd([
                (b"a", vb(b"value a")),
                (
                    b"nested",
                    vd([
                        (b"b", vb(b"value b")),
                        (
                            b"nested",
                            vd([(b"c", vb(b"value c")), (b"nested", vb(b"value d"))]),
                        ),
                    ]),
                ),
            ])
            .to_own::<Bytes>()),
        );

        assert_eq!(
            ser::to_bytes(&value),
            Ok(Bytes::from_static(b"d1:a7:value a6:nestedfoobare")),
        );
    }
}
