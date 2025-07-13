use std::fmt;
use std::net::{SocketAddr, SocketAddrV4};

use bytes::{Bytes, BytesMut};
use serde::de::{Deserialize, Deserializer, Error as _};
use serde::ser::{Serialize, Serializer};

use bt_base::NodeId;
use bt_base::compact::{CompactDecode, CompactEncode};
use bt_bencode::Value;
use bt_serde::SerdeWith;

use crate::reinsert::ToValue;

//
// TODO: Support IPv6.
//

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct NodeInfo {
    pub id: NodeId,
    pub endpoint: SocketAddr,
}

impl fmt::Display for NodeInfo {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "({}, {})", self.id, self.endpoint)
    }
}

type CompactNodeInfoV4 = (NodeId, SocketAddrV4);

impl TryFrom<NodeInfo> for CompactNodeInfoV4 {
    type Error = NodeInfo;

    fn try_from(info: NodeInfo) -> Result<Self, Self::Error> {
        match info.endpoint {
            SocketAddr::V4(endpoint) => Ok((info.id, endpoint)),
            SocketAddr::V6(_) => Err(info),
        }
    }
}

impl From<CompactNodeInfoV4> for NodeInfo {
    fn from((id, endpoint): CompactNodeInfoV4) -> Self {
        Self {
            id,
            endpoint: endpoint.into(),
        }
    }
}

pub(crate) struct CompactNodeInfoListSerdeWithV4;

impl SerdeWith for CompactNodeInfoListSerdeWithV4 {
    type Value = Vec<NodeInfo>;

    fn deserialize<'de, D>(deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        match CompactNodeInfoV4::decode_many(&Bytes::deserialize(deserializer)?) {
            Ok(nodes) => Ok(nodes.map(NodeInfo::from).collect()),
            Err(error) => Err(D::Error::custom(error)),
        }
    }

    fn serialize<S>(value: &Self::Value, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        encode_list_v4(value).serialize(serializer)
    }
}

impl ToValue for Vec<NodeInfo> {
    fn to_value(self) -> Value {
        Value::ByteString(encode_list_v4(&self).freeze())
    }
}

fn encode_list_v4(node_info_list: &[NodeInfo]) -> BytesMut {
    let mut buffer = BytesMut::new();
    CompactNodeInfoV4::encode_many(
        node_info_list
            .iter()
            .cloned()
            .map(|info| CompactNodeInfoV4::try_from(info).expect("ipv4")),
        &mut buffer,
    );
    buffer
}

#[cfg(test)]
mod tests {
    use serde::de::value::{BytesDeserializer, Error};

    use bt_bencode::bencode;
    use bt_bencode::value::ser::Serializer;

    use super::*;

    #[test]
    fn serde_with() {
        assert_eq!(
            CompactNodeInfoListSerdeWithV4::deserialize(BytesDeserializer::<Error>::new(&[])),
            Ok(vec![]),
        );
        assert_eq!(
            CompactNodeInfoListSerdeWithV4::serialize(&vec![], Serializer::new()),
            Ok(bencode!(b"")),
        );

        let one = [1u8; 20];
        let two = [2u8; 20];
        let node_info_list = vec![
            NodeInfo {
                id: one.into(),
                endpoint: "127.0.0.1:8001".parse().unwrap(),
            },
            NodeInfo {
                id: two.into(),
                endpoint: "127.0.0.2:8002".parse().unwrap(),
            },
        ];
        let mut compact = Vec::new();
        compact.extend_from_slice(&one);
        compact.extend_from_slice(b"\x7f\x00\x00\x01\x1f\x41");
        compact.extend_from_slice(&two);
        compact.extend_from_slice(b"\x7f\x00\x00\x02\x1f\x42");
        assert_eq!(
            CompactNodeInfoListSerdeWithV4::deserialize(BytesDeserializer::<Error>::new(&compact)),
            Ok(node_info_list.clone()),
        );
        assert_eq!(
            CompactNodeInfoListSerdeWithV4::serialize(&node_info_list, Serializer::new()),
            Ok(bencode!(compact)),
        );
    }
}
