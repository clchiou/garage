use std::fmt;

use serde::ser::{Serialize, SerializeMap, SerializeSeq, Serializer};

use crate::value::Value;

use super::{BYTES_TAG, Yaml};

impl<B> Serialize for Yaml<&Value<B>>
where
    B: AsRef<[u8]>,
{
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        match self.0 {
            Value::ByteString(bytes) => SerializeBytes(bytes).serialize(serializer),
            Value::Integer(integer) => serializer.serialize_i64(*integer),
            Value::List(list) => {
                let mut seq = serializer.serialize_seq(Some(list.len()))?;
                for element in list {
                    seq.serialize_element(&Self(element))?;
                }
                seq.end()
            }
            Value::Dictionary(dict) => {
                let mut map = serializer.serialize_map(Some(dict.len()))?;
                for (k, v) in dict {
                    map.serialize_entry(&SerializeBytes(k), &Self(v))?;
                }
                map.end()
            }
        }
    }
}

struct SerializeBytes<'a, B>(&'a B);

impl<B> Serialize for SerializeBytes<'_, B>
where
    B: AsRef<[u8]>,
{
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let bytes = self.0.as_ref();
        match str::from_utf8(bytes) {
            Ok(string) => serializer.serialize_str(string),
            Err(_) => serializer.serialize_newtype_variant(
                "",
                0,
                BYTES_TAG,
                &CollectStr(bytes.escape_ascii()),
            ),
        }
    }
}

struct CollectStr<T>(T);

impl<T> Serialize for CollectStr<T>
where
    T: fmt::Display,
{
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.collect_str(&self.0)
    }
}

#[cfg(test)]
mod tests {
    use bytes::Bytes;

    use crate::testing::{BENCODE, REDUCED_YAML};

    use super::*;

    #[test]
    fn to_yaml() {
        assert_eq!(
            serde_yaml::to_value(&Yaml(&*BENCODE)).unwrap(),
            *REDUCED_YAML,
        );
        assert_eq!(
            serde_yaml::to_value(&Yaml(&BENCODE.to_own::<Bytes>())).unwrap(),
            *REDUCED_YAML,
        );
    }
}
