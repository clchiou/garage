use serde::de::{Deserialize, Deserializer};
use serde::ser::{Serialize, Serializer};
use serde_bytes::{ByteArray, Bytes};

use bt_base::node_id::{NODE_ID_SIZE, NodeId};
use bt_bencode::own::bytes::{ByteString, Value};
use bt_serde::SerdeWith;

use crate::reinsert::ToValue;

pub(crate) struct NodeIdSerdeWith;

impl SerdeWith for NodeIdSerdeWith {
    type Value = NodeId;

    fn deserialize<'de, D>(deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        ByteArray::<NODE_ID_SIZE>::deserialize(deserializer).map(|bytes| bytes.into_array().into())
    }

    fn serialize<S>(value: &Self::Value, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        Bytes::new(value.as_ref()).serialize(serializer)
    }
}

impl ToValue for NodeId {
    fn to_value(self) -> Value {
        Value::ByteString(ByteString::copy_from_slice(self.as_ref()))
    }
}

#[cfg(test)]
mod tests {
    use serde::de::value::{BytesDeserializer, Error};

    use bt_bencode::bencode;
    use bt_bencode::value::ser::Serializer;

    use super::*;

    #[test]
    fn serde_with() {
        let zero = [0u8; 20];
        let node_id = NodeId::from(zero);
        assert_eq!(
            NodeIdSerdeWith::deserialize(BytesDeserializer::<Error>::new(&zero)),
            Ok(node_id.clone()),
        );
        assert_eq!(
            NodeIdSerdeWith::serialize(&node_id, Serializer::new()),
            Ok(bencode!(zero)),
        );
    }

    #[test]
    fn to_value() {
        let zero = [0u8; 20];
        assert_eq!(NodeId::from(zero).to_value(), bencode!(zero));
    }
}
