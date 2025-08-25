use std::time::Duration;

use serde::{Deserialize, Deserializer, Serialize, Serializer};

use bt_base::{PeerEndpoint, PeerId};
use bt_bencode::Value;
use bt_serde::SerdeWith;

#[bt_serde::optional]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct ResponseOrFailure {
    #[serde(rename = "failure reason")]
    pub failure_reason: Option<String>,

    #[serde(flatten)]
    pub response: Response,
}

#[bt_serde::optional]
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct Response {
    //
    // BEP 3
    //
    #[serde(
        default,
        skip_serializing_if = "Duration::is_zero",
        with = "DurationSerdeWith"
    )]
    pub interval: Duration,

    #[serde(default, skip_serializing_if = "Peers::is_empty")]
    pub peers: Peers,

    //
    // BEP 3, allegedly (I cannot find them in the BEP text).
    //
    #[serde(rename = "warning message")]
    pub warning_message: Option<String>,

    #[serde(rename = "min interval")]
    #[optional(with = "DurationSerdeWith")]
    pub min_interval: Option<Duration>,

    #[serde(rename = "tracker id")]
    pub tracker_id: Option<String>,

    pub complete: Option<usize>,
    pub incomplete: Option<usize>,

    //
    // BEP 7
    //
    #[serde(default, skip_serializing_if = "Vec::is_empty", with = "peers6")]
    pub peers6: Vec<PeerEndpoint>,

    //
    // Misc
    //
    #[serde(flatten)]
    pub extra: Value,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Peers {
    PeerEndpoint(Vec<PeerEndpoint>), // BEP 23
    PeerInfo(Vec<PeerInfo>),         // BEP 3
}

#[bt_serde::optional]
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct PeerInfo {
    #[serde(rename = "peer id")]
    pub id: Option<PeerId>,
    pub ip: String,
    pub port: u16,

    #[serde(flatten)]
    pub extra: Value,
}

impl Default for Peers {
    fn default() -> Self {
        Peers::PeerEndpoint(Default::default())
    }
}

impl Peers {
    fn is_empty(&self) -> bool {
        match self {
            Self::PeerEndpoint(peers) => peers.is_empty(),
            Self::PeerInfo(peers) => peers.is_empty(),
        }
    }
}

struct DurationSerdeWith;

impl SerdeWith for DurationSerdeWith {
    type Value = Duration;

    fn deserialize<'de, D>(deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        u64::deserialize(deserializer).map(Duration::from_secs)
    }

    fn serialize<S>(duration: &Self::Value, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        duration.as_secs().serialize(serializer)
    }
}

mod peers {
    use serde::de::Error;
    use serde::{Deserialize, Deserializer, Serialize, Serializer};

    use bt_base::peer_endpoint::v4;
    use bt_bencode::Value;

    use super::Peers;

    impl<'de> Deserialize<'de> for Peers {
        fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
        where
            D: Deserializer<'de>,
        {
            match Value::deserialize(deserializer)? {
                Value::ByteString(compact) => match v4::decode_many(&compact) {
                    Ok(peers) => Ok(Self::PeerEndpoint(peers.collect())),
                    Err(error) => Err(D::Error::custom(error)),
                },
                peers => match bt_bencode::from_value(peers) {
                    Ok(peers) => Ok(Self::PeerInfo(peers)),
                    Err(error) => Err(D::Error::custom(error)),
                },
            }
        }
    }

    impl Serialize for Peers {
        fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
        where
            S: Serializer,
        {
            match self {
                Self::PeerEndpoint(peers) => v4::to_buffer(peers).serialize(serializer),
                Self::PeerInfo(peers) => peers.serialize(serializer),
            }
        }
    }
}

mod peers6 {
    use bytes::Bytes;
    use serde::de::Error;
    use serde::{Deserialize, Deserializer, Serialize, Serializer};

    use bt_base::peer_endpoint::{PeerEndpoint, v6};

    pub(super) fn deserialize<'de, D>(deserializer: D) -> Result<Vec<PeerEndpoint>, D::Error>
    where
        D: Deserializer<'de>,
    {
        match v6::decode_many(&Bytes::deserialize(deserializer)?) {
            Ok(peers) => Ok(peers.collect()),
            Err(error) => Err(D::Error::custom(error)),
        }
    }

    pub(super) fn serialize<S>(peers: &[PeerEndpoint], serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        v6::to_buffer(peers).serialize(serializer)
    }
}

#[cfg(test)]
mod tests {
    use bytes::Bytes;

    use bt_bencode::bencode;

    use super::*;

    #[test]
    fn response() {
        for (testdata, mut bencode) in [
            (Default::default(), b"de" as &[u8]),
            (
                ResponseOrFailure {
                    failure_reason: Some("spam egg".to_string()),
                    response: Default::default(),
                },
                b"d14:failure reason8:spam egge" as &[u8],
            ),
        ] {
            assert_eq!(
                bt_bencode::to_bytes(&testdata).unwrap(),
                // `Bytes` output looks nicer.
                Bytes::copy_from_slice(bencode),
            );
            assert_eq!(
                bt_bencode::from_buf::<_, ResponseOrFailure>(&mut bencode).unwrap(),
                testdata,
            );
        }

        for (testdata, mut bencode) in [
            (Default::default(), b"de" as &[u8]),
            (
                Response {
                    interval: Duration::from_secs(42),
                    ..Default::default()
                },
                b"d8:intervali42ee",
            ),
            (
                Response {
                    peers: Peers::PeerEndpoint(vec![
                       "127.0.0.1:1".parse().unwrap(),
                       "127.0.0.2:2".parse().unwrap(),
                    ]),
                    ..Default::default()
                },
                b"d5:peers12:\x7f\x00\x00\x01\x00\x01\x7f\x00\x00\x02\x00\x02e",
            ),
            (
                Response {
                    peers: Peers::PeerInfo(vec![
                        PeerInfo {
                            id: Some("0123456789abcdefghij".parse().unwrap()),
                            ip: "localhost:1".to_string(),
                            port: 1,
                            extra: bencode!({b"foo": b"bar"}),
                        },
                        PeerInfo {
                            id: None,
                            ip: "127.0.0.2:2".to_string(),
                            port: 2,
                            extra: bencode!({}),
                        },
                    ]),
                    ..Default::default()
                },
                b"d5:peersld3:foo3:bar2:ip11:localhost:17:peer id20:0123456789abcdefghij4:porti1eed2:ip11:127.0.0.2:24:porti2eeee",
            ),
            (
                Response {
                    warning_message: Some("spam egg".to_string()),
                    ..Default::default()
                },
                b"d15:warning message8:spam egge",
            ),
            (
                Response {
                    min_interval: Some(Duration::from_secs(42)),
                    ..Default::default()
                },
                b"d12:min intervali42ee",
            ),
            (
                Response {
                    tracker_id: Some("spam egg".to_string()),
                    ..Default::default()
                },
                b"d10:tracker id8:spam egge",
            ),
            (
                Response {
                    complete: Some(1),
                    incomplete: Some(2),
                    ..Default::default()
                },
                b"d8:completei1e10:incompletei2ee",
            ),
            (
                Response {
                    extra: bencode!({b"foo": b"bar"}),
                    ..Default::default()
                },
                b"d3:foo3:bare",
            ),
        ] {
            assert_eq!(
                bt_bencode::to_bytes(&testdata).unwrap(),
                // `Bytes` output looks nicer.
                Bytes::copy_from_slice(bencode),
            );
            assert_eq!(
                bt_bencode::from_buf::<_, Response>(&mut bencode).unwrap(),
                testdata,
            );
        }
    }
}
