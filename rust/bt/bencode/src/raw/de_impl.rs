use std::fmt;
use std::marker::PhantomData;

use bytes::Bytes;
use serde::de::{self, Deserialize, Deserializer, Error as _, SeqAccess};

use super::{MAGIC, WithRaw};

impl<'de, T> Deserialize<'de> for WithRaw<T, Bytes>
where
    T: Deserialize<'de>,
{
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_newtype_struct(MAGIC, Visitor::new())
    }
}

impl<'de: 'a, 'a, T> Deserialize<'de> for WithRaw<T, &'a [u8]>
where
    T: Deserialize<'de>,
{
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_newtype_struct(MAGIC, Visitor::new())
    }
}

struct Visitor<T, D>(PhantomData<(T, D)>);

impl<T, D> Visitor<T, D> {
    fn new() -> Self {
        Self(PhantomData)
    }
}

impl<'de, T, D> de::Visitor<'de> for Visitor<T, D>
where
    T: Deserialize<'de>,
    D: Deserialize<'de>,
{
    type Value = WithRaw<T, D>;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("(T, D) tuple")
    }

    fn visit_seq<A>(self, mut seq: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        Ok(WithRaw(
            seq.next_element()?
                .ok_or_else(|| A::Error::invalid_length(0, &self))?,
            seq.next_element()?
                .ok_or_else(|| A::Error::invalid_length(1, &self))?,
        ))
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use crate::testing::{NestedA, NestedB, NestedC, vi};
    use crate::value;

    use super::*;

    #[test]
    fn deserialize_from_value() {
        assert_matches!(
            value::de::from_borrowed_value::<WithRaw<u8, &[u8]>>(vi(0)),
            Err(error)
            if error.to_string() == "deserializing raw bencode from value is not supported for now",
        );
    }

    #[test]
    fn deserialize_from_bytes() {
        let testdata = b"i1e";

        assert_eq!(
            crate::de::from_slice(&mut testdata.as_slice()),
            Ok(WithRaw(1u8, testdata.as_slice())),
        );

        let testdata = Bytes::from_static(testdata);
        assert_eq!(
            crate::de::from_buf(testdata.clone()),
            Ok(WithRaw(1u8, testdata)),
        );
    }

    #[test]
    fn nested() {
        let raw_d = /************************************************************/ b"7:value d";
        let raw_c = /***************************************/ b"d1:c7:value c6:nested7:value de";
        let raw_b = /******************/ b"d1:b7:value b6:nestedd1:c7:value c6:nested7:value dee";
        let raw_a = b"d1:a7:value a6:nestedd1:b7:value b6:nestedd1:c7:value c6:nested7:value deee";

        let d = WithRaw("value d".to_string(), Bytes::from_static(raw_d));
        let c = WithRaw(
            NestedC {
                c: "value c".to_string(),
                nested: d.clone(),
            },
            Bytes::from_static(raw_c),
        );
        let b = WithRaw(
            NestedB {
                b: "value b".to_string(),
                nested: c.clone(),
            },
            Bytes::from_static(raw_b),
        );
        let a = WithRaw(
            NestedA {
                a: "value a".to_string(),
                nested: b.clone(),
            },
            Bytes::from_static(raw_a),
        );

        assert_eq!(crate::de::from_slice(&mut raw_d.as_slice()), Ok(d));
        assert_eq!(crate::de::from_slice(&mut raw_c.as_slice()), Ok(c));
        assert_eq!(crate::de::from_slice(&mut raw_b.as_slice()), Ok(b));
        assert_eq!(crate::de::from_slice(&mut raw_a.as_slice()), Ok(a));
    }
}
