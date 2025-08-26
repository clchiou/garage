use std::fmt;

use serde::de::{Deserialize, Deserializer, SeqAccess, Visitor};
use serde::ser::{Serialize, SerializeSeq, Serializer};
use serde_bytes::ByteArray;

use bt_base::peer_endpoint::{PeerEndpoint, v4};
use bt_bencode::Value;
use bt_serde::SerdeWith;

use crate::reinsert::ToValue;

//
// TODO: Support IPv6.
//

pub(crate) struct CompactPeerEndpointListSerdeWithV4;

struct CompactPeerEndpointListSerdeV4<T>(T);

struct CompactPeerEndpointListVisitorV4;

impl SerdeWith for CompactPeerEndpointListSerdeWithV4 {
    type Value = Vec<PeerEndpoint>;

    fn deserialize<'de, D>(deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        Ok(CompactPeerEndpointListSerdeV4::deserialize(deserializer)?.0)
    }

    fn serialize<S>(value: &Self::Value, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        CompactPeerEndpointListSerdeV4(value).serialize(serializer)
    }
}

impl ToValue for Vec<PeerEndpoint> {
    fn to_value(self) -> Value {
        Value::List(v4::to_bytes_iter(&self).map(Value::ByteString).collect())
    }
}

impl<'de> Deserialize<'de> for CompactPeerEndpointListSerdeV4<Vec<PeerEndpoint>> {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_seq(CompactPeerEndpointListVisitorV4)
    }
}

impl<'de> Visitor<'de> for CompactPeerEndpointListVisitorV4 {
    type Value = CompactPeerEndpointListSerdeV4<Vec<PeerEndpoint>>;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("any compact peer endpoint list")
    }

    fn visit_seq<A>(self, mut seq: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut list = Vec::with_capacity(seq.size_hint().unwrap_or(0));
        while let Some(item) = seq.next_element::<ByteArray<{ v4::SIZE }>>()? {
            list.push(v4::decode(&*item).expect("decode"));
        }
        Ok(CompactPeerEndpointListSerdeV4(list))
    }
}

impl Serialize for CompactPeerEndpointListSerdeV4<&Vec<PeerEndpoint>> {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let mut seq = serializer.serialize_seq(Some(self.0.len()))?;
        for array in v4::to_array_iter(self.0) {
            seq.serialize_element(&ByteArray::from(array))?;
        }
        seq.end()
    }
}

#[cfg(test)]
mod tests {
    use serde::de::IntoDeserializer;
    use serde::de::value::{BytesDeserializer, Error};

    use bt_bencode::bencode;
    use bt_bencode::value::ser::Serializer;

    use super::*;

    #[test]
    fn serde_with() {
        assert_eq!(
            CompactPeerEndpointListSerdeWithV4::deserialize(
                Vec::<BytesDeserializer<Error>>::new().into_deserializer(),
            ),
            Ok(vec![]),
        );
        assert_eq!(
            CompactPeerEndpointListSerdeWithV4::serialize(&vec![], Serializer::new()),
            Ok(bencode!([])),
        );

        let peer_endpoint_list = vec![
            "127.0.0.1:8001".parse().unwrap(),
            "127.0.0.2:8002".parse().unwrap(),
        ];
        let mut deserializer = Vec::new();
        deserializer.push(BytesDeserializer::<Error>::new(b"\x7f\x00\x00\x01\x1f\x41"));
        deserializer.push(BytesDeserializer::<Error>::new(b"\x7f\x00\x00\x02\x1f\x42"));
        assert_eq!(
            CompactPeerEndpointListSerdeWithV4::deserialize(deserializer.into_deserializer()),
            Ok(peer_endpoint_list.clone()),
        );
        assert_eq!(
            CompactPeerEndpointListSerdeWithV4::serialize(&peer_endpoint_list, Serializer::new()),
            Ok(bencode!([
                b"\x7f\x00\x00\x01\x1f\x41",
                b"\x7f\x00\x00\x02\x1f\x42",
            ])),
        );
    }

    #[test]
    fn to_value() {
        assert_eq!(Vec::<PeerEndpoint>::new().to_value(), bencode!([]));

        assert_eq!(
            vec![
                "127.0.0.1:8001".parse::<PeerEndpoint>().unwrap(),
                "127.0.0.2:8002".parse().unwrap(),
            ]
            .to_value(),
            bencode!([b"\x7f\x00\x00\x01\x1f\x41", b"\x7f\x00\x00\x02\x1f\x42"]),
        );
    }
}
