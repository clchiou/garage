use serde::ser::{Serialize, SerializeMap, SerializeSeq, Serializer};
use serde_bytes::Bytes;

use super::Value;

impl<B> Serialize for Value<B>
where
    B: AsRef<[u8]>,
{
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        match self {
            Self::ByteString(bytes) => serializer.serialize_bytes(bytes.as_ref()),
            Self::Integer(integer) => serializer.serialize_i64(*integer),
            Self::List(list) => {
                let mut seq = serializer.serialize_seq(Some(list.len()))?;
                for element in list {
                    seq.serialize_element(element)?;
                }
                seq.end()
            }
            Self::Dictionary(dict) => {
                let mut map = serializer.serialize_map(Some(dict.len()))?;
                for (k, v) in dict {
                    map.serialize_entry(Bytes::new(k.as_ref()), v)?;
                }
                map.end()
            }
        }
    }
}
