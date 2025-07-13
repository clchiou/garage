// BEP 42 DHT Security Extension

use std::net::SocketAddrV4;

use serde::de::{Deserialize, Deserializer, Error as _};
use serde::ser::{Serialize, Serializer};
use serde_bytes::ByteArray;

use bt_base::compact::{CompactDecode, CompactEncode, CompactSize};
use bt_serde::SerdeWith;

// TODO: Support IPv6.
pub type Requestor = SocketAddrV4;

pub(crate) struct CompactRequestorSerdeWith;

impl SerdeWith for CompactRequestorSerdeWith {
    type Value = Requestor;

    fn deserialize<'de, D>(deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        Requestor::decode(&*ByteArray::<{ Requestor::SIZE }>::deserialize(
            deserializer,
        )?)
        .map_err(D::Error::custom)
    }

    fn serialize<S>(value: &Self::Value, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let mut buffer = ByteArray::<{ Requestor::SIZE }>::default();
        Requestor::encode(value, buffer.as_mut_slice());
        buffer.serialize(serializer)
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
        let requestor = "127.0.0.1:8001".parse().unwrap();
        let compact = b"\x7f\x00\x00\x01\x1f\x41";
        assert_eq!(
            CompactRequestorSerdeWith::deserialize(BytesDeserializer::<Error>::new(compact)),
            Ok(requestor),
        );
        assert_eq!(
            CompactRequestorSerdeWith::serialize(&requestor, Serializer::new()),
            Ok(bencode!(compact)),
        );
    }
}
