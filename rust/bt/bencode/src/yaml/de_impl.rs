use std::fmt;
use std::marker::PhantomData;

use serde::de::{
    self, Deserialize, Deserializer, EnumAccess, Error as _, MapAccess, SeqAccess, VariantAccess,
};

use g1_base::slice::ByteSliceExt;

use crate::bstr::OwnedBStr;

use crate::value::{self, Dictionary, List, Value};

use super::{BYTES_TAG, Yaml};

//
// NOTE: We cannot implement `Deserialize` for `Yaml<Value<&[u8]>>` because we cannot borrow from
// the result of unescaping a `!bytes`-tagged string.
//

impl<'de, B> Deserialize<'de> for Yaml<Value<B>>
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

struct Visitor<B>(value::de_impl::Visitor<B>);

impl<B> Visitor<B> {
    fn new() -> Self {
        Self(value::de_impl::Visitor::new())
    }
}

macro_rules! impl_forwarders {
    ($($name:ident => $type:ty),* $(,)?) => {
        $(
            fn $name<E>(self, value: $type) -> Result<Self::Value, E>
            where
                E: de::Error,
            {
                self.0.$name(value).map(Yaml)
            }
        )*
    };
}

impl<'de, B> de::Visitor<'de> for Visitor<B>
where
    B: Deserialize<'de>, // Required by `value::de_impl::Visitor`.
    B: OwnedBStr,
{
    type Value = Yaml<Value<B>>;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("any valid bencode-compatible yaml value")
    }

    impl_forwarders!(
        visit_bool => bool,
        visit_i8 => i8,
        visit_i16 => i16,
        visit_i32 => i32,
        visit_i64 => i64,
        visit_i128 => i128,
        visit_u8 => u8,
        visit_u16 => u16,
        visit_u32 => u32,
        visit_u64 => u64,
        visit_u128 => u128,
        visit_f32 => f32,
        visit_f64 => f64,
        visit_char => char,
        visit_str => &str,
        visit_borrowed_str => &'de str,
        visit_string => String,
        visit_bytes => &[u8],
        visit_borrowed_bytes => &'de [u8],
        visit_byte_buf => Vec<u8>,
    );

    fn visit_none<E>(self) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        self.0.visit_none().map(Yaml)
    }

    fn visit_some<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        let Yaml(value) = deserializer.deserialize_any(self)?;
        Ok(Yaml(Value::List([value].into())))
    }

    fn visit_unit<E>(self) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        self.0.visit_unit().map(Yaml)
    }

    fn visit_newtype_struct<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(self)
    }

    fn visit_seq<A>(self, mut seq: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut list = List::with_capacity(seq.size_hint().unwrap_or(0));
        while let Some(Yaml(item)) = seq.next_element()? {
            list.push(item);
        }
        Ok(Yaml(Value::List(list)))
    }

    fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut dict = Dictionary::new();
        while let Some((YamlStr(key), Yaml(value))) = map.next_entry()? {
            dict.insert(key, value);
        }
        Ok(Yaml(Value::Dictionary(dict)))
    }

    fn visit_enum<A>(self, data: A) -> Result<Self::Value, A::Error>
    where
        A: EnumAccess<'de>,
    {
        let (variant, value) = data.variant::<String>()?;
        Ok(Yaml(if variant == BYTES_TAG {
            Value::ByteString(unescape(value.newtype_variant()?)?)
        } else {
            // Unrecognizable tags are preserved as they are.
            let variant = B::from_bytes(variant.as_bytes());
            let Yaml(value) = value.newtype_variant()?;
            Value::Dictionary([(variant, value)].into())
        }))
    }
}

struct YamlStr<B>(B);

impl<'de, B> Deserialize<'de> for YamlStr<B>
where
    B: OwnedBStr,
{
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_any(YamlStrVisitor::new())
    }
}

struct YamlStrVisitor<B>(PhantomData<B>);

impl<B> YamlStrVisitor<B> {
    fn new() -> Self {
        Self(PhantomData)
    }
}

impl<'de, B> de::Visitor<'de> for YamlStrVisitor<B>
where
    B: OwnedBStr,
{
    type Value = YamlStr<B>;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("any valid bencode-compatible yaml string")
    }

    fn visit_bytes<E>(self, value: &[u8]) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(YamlStr(B::from_bytes(value)))
    }

    fn visit_byte_buf<E>(self, value: Vec<u8>) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(YamlStr(B::from_byte_buf(value)))
    }

    fn visit_borrowed_bytes<E>(self, value: &'de [u8]) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(YamlStr(B::from_bytes(value)))
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

    fn visit_enum<A>(self, data: A) -> Result<Self::Value, A::Error>
    where
        A: EnumAccess<'de>,
    {
        let (variant, value) = data.variant::<String>()?;
        if variant == BYTES_TAG {
            Ok(YamlStr(unescape(value.newtype_variant()?)?))
        } else {
            Err(A::Error::unknown_variant(&variant, &[BYTES_TAG]))
        }
    }
}

fn unescape<B, E>(escaped: String) -> Result<B, E>
where
    B: OwnedBStr,
    E: de::Error,
{
    match escaped.as_bytes().unescape_ascii().try_collect() {
        Ok(bytes) => Ok(B::from_byte_buf(bytes)),
        Err(error) => Err(E::custom(error)),
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use bytes::Bytes;
    use serde::de::Deserialize;

    use crate::testing::{
        BENCODE, EXTENDED_BENCODE, REDUCED_YAML, TAG_BENCODE, TAG_YAML, YAML, yb, yd, yi, yt,
    };
    use crate::value::Value;

    use super::*;

    fn test_from_str(testdata: &str, expect: &Value<&[u8]>) {
        //
        // * An adapter is required when calling `serde_yaml::from_str` because
        //   `serde_yaml::de::Deserializer` refuse to return raw UTF-8 byte strings (whereas
        //   `serde_json` has no problem with that).
        //
        // * No test for a borrowed `Value`, because `Deserialize` cannot be implemented for it.
        //
        assert_matches!(
            serde_yaml::from_str::<Value<Bytes>>(&testdata),
            Err(error)
            if error.to_string() == "serialization and deserialization of bytes in YAML is not implemented",
        );
        assert_eq!(
            serde_yaml::from_str::<Yaml<Value<Bytes>>>(&testdata).unwrap(),
            Yaml(expect.to_own()),
        );
    }

    #[test]
    fn from_yaml() {
        assert_eq!(
            <Value<&[u8]>>::deserialize(&*YAML).unwrap(),
            *EXTENDED_BENCODE,
        );
        assert_matches!(
            <Value<&[u8]>>::deserialize(yb("foo bar")),
            Err(error)
            if error.to_string() == "borrow from owned byte string: b\"foo bar\"",
        );
        assert_eq!(
            serde_yaml::from_value::<Value<Bytes>>(YAML.clone()).unwrap(),
            EXTENDED_BENCODE.to_own(),
        );

        test_from_str(&serde_yaml::to_string(&*YAML).unwrap(), &*EXTENDED_BENCODE);
    }

    #[test]
    fn from_yaml_tagged_nodes() {
        for (testdata, expect) in [(&*TAG_YAML, &*TAG_BENCODE), (&*REDUCED_YAML, &*BENCODE)] {
            // No test for a borrowed `Value`, because `Deserialize` cannot be implemented for it.
            assert_matches!(
                serde_yaml::from_value::<Value<Bytes>>(testdata.clone()),
                Err(error)
                if error.to_string() == "invalid type: enum, expected any valid bencode value",
            );
            assert_eq!(
                serde_yaml::from_value::<Yaml<Value<Bytes>>>(testdata.clone()).unwrap(),
                Yaml(expect.to_own()),
            );

            test_from_str(&serde_yaml::to_string(testdata).unwrap(), expect);
        }

        let mut testdata = yd([]);
        testdata
            .as_mapping_mut()
            .expect("map")
            .insert(yt("wrong_tag", yb("x")), yi(0));
        assert_matches!(
            serde_yaml::from_value::<Yaml<Value<Bytes>>>(testdata.clone()),
            Err(error)
            if error.to_string() == "unknown variant `wrong_tag`, expected `bytes`",
        );
        // I do not know why, but `serde_yaml::to_string(&testdata)` fails.
        let testdata = "!wrong_tag x: 1";
        assert_matches!(
            serde_yaml::from_str::<Yaml<Value<Bytes>>>(testdata),
            Err(error)
            if error.to_string() == "unknown variant `wrong_tag`, expected `bytes`",
        );
    }
}
