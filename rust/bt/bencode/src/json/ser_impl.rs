use serde::ser::{Serialize, SerializeMap, SerializeSeq, Serializer};

use crate::value::Value;

use super::Json;

impl<B> Serialize for Json<&Value<B>>
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
            Err(_) => serializer.collect_str(&bytes.escape_ascii()),
        }
    }
}

#[cfg(test)]
mod tests {
    use bytes::Bytes;

    use crate::testing::{BENCODE, REDUCED_JSON};

    use super::*;

    #[test]
    fn to_json() {
        assert_eq!(
            serde_json::to_value(&Json(&*BENCODE)).unwrap(),
            *REDUCED_JSON,
        );
        assert_eq!(
            serde_json::to_value(&Json(&BENCODE.to_own::<Bytes>())).unwrap(),
            *REDUCED_JSON,
        );
    }
}
