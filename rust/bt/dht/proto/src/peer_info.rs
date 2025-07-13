use std::fmt;
use std::net::{SocketAddr, SocketAddrV4};

use bytes::BytesMut;
use serde::de::{Deserialize, Deserializer, SeqAccess, Visitor};
use serde::ser::{Serialize, SerializeSeq, Serializer};
use serde_bytes::ByteArray;

use bt_base::compact::{CompactDecode, CompactEncode, CompactSize};
use bt_bencode::Value;
use bt_serde::SerdeWith;

use crate::reinsert::ToValue;

//
// TODO: Support IPv6.
//

pub type PeerInfo = SocketAddr;

type CompactPeerInfoV4 = SocketAddrV4;

pub(crate) struct CompactPeerInfoListSerdeWithV4;

struct CompactPeerInfoListSerdeV4<T>(T);

struct CompactPeerInfoListVisitorV4;

fn to_compact_v4(info: PeerInfo) -> CompactPeerInfoV4 {
    match info {
        SocketAddr::V4(info) => info,
        SocketAddr::V6(_) => panic!("expect ipv4: {info}"),
    }
}

impl SerdeWith for CompactPeerInfoListSerdeWithV4 {
    type Value = Vec<PeerInfo>;

    fn deserialize<'de, D>(deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        Ok(CompactPeerInfoListSerdeV4::deserialize(deserializer)?.0)
    }

    fn serialize<S>(value: &Self::Value, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        CompactPeerInfoListSerdeV4(value).serialize(serializer)
    }
}

impl ToValue for Vec<PeerInfo> {
    fn to_value(self) -> Value {
        let mut buffer = BytesMut::with_capacity(self.len() * CompactPeerInfoV4::SIZE);
        CompactPeerInfoV4::encode_many(self.into_iter().map(to_compact_v4), &mut buffer);
        Value::List(
            CompactPeerInfoV4::split(buffer.freeze())
                .expect("split")
                .map(Value::ByteString)
                .collect(),
        )
    }
}

impl<'de> Deserialize<'de> for CompactPeerInfoListSerdeV4<Vec<PeerInfo>> {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_seq(CompactPeerInfoListVisitorV4)
    }
}

impl<'de> Visitor<'de> for CompactPeerInfoListVisitorV4 {
    type Value = CompactPeerInfoListSerdeV4<Vec<PeerInfo>>;

    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("any compact peer info list")
    }

    fn visit_seq<A>(self, mut seq: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut list = Vec::with_capacity(seq.size_hint().unwrap_or(0));
        while let Some(item) = seq.next_element::<ByteArray<{ CompactPeerInfoV4::SIZE }>>()? {
            list.push(CompactPeerInfoV4::decode(&*item).expect("decode").into());
        }
        Ok(CompactPeerInfoListSerdeV4(list))
    }
}

impl Serialize for CompactPeerInfoListSerdeV4<&Vec<PeerInfo>> {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let mut seq = serializer.serialize_seq(Some(self.0.len()))?;
        let mut buffer = ByteArray::<{ CompactPeerInfoV4::SIZE }>::default();
        for info in self.0 {
            CompactPeerInfoV4::encode(&to_compact_v4(*info), buffer.as_mut_slice());
            seq.serialize_element(&buffer)?;
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
            CompactPeerInfoListSerdeWithV4::deserialize(
                Vec::<BytesDeserializer<Error>>::new().into_deserializer(),
            ),
            Ok(vec![]),
        );
        assert_eq!(
            CompactPeerInfoListSerdeWithV4::serialize(&vec![], Serializer::new()),
            Ok(bencode!([])),
        );

        let peer_info_list = vec![
            "127.0.0.1:8001".parse().unwrap(),
            "127.0.0.2:8002".parse().unwrap(),
        ];
        let mut deserializer = Vec::new();
        deserializer.push(BytesDeserializer::<Error>::new(b"\x7f\x00\x00\x01\x1f\x41"));
        deserializer.push(BytesDeserializer::<Error>::new(b"\x7f\x00\x00\x02\x1f\x42"));
        assert_eq!(
            CompactPeerInfoListSerdeWithV4::deserialize(deserializer.into_deserializer()),
            Ok(peer_info_list.clone()),
        );
        assert_eq!(
            CompactPeerInfoListSerdeWithV4::serialize(&peer_info_list, Serializer::new()),
            Ok(bencode!([
                b"\x7f\x00\x00\x01\x1f\x41",
                b"\x7f\x00\x00\x02\x1f\x42",
            ])),
        );
    }

    #[test]
    fn to_value() {
        assert_eq!(Vec::<PeerInfo>::new().to_value(), bencode!([]));

        assert_eq!(
            vec![
                "127.0.0.1:8001".parse::<PeerInfo>().unwrap(),
                "127.0.0.2:8002".parse().unwrap(),
            ]
            .to_value(),
            bencode!([b"\x7f\x00\x00\x01\x1f\x41", b"\x7f\x00\x00\x02\x1f\x42"]),
        );
    }
}
