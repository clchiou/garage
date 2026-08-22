use std::marker::PhantomData;

use chrono::{DateTime, SecondsFormat, Utc};
use serde::de::{Deserialize, Deserializer, Error as _};
use serde::ser::{Serialize, Serializer};
use serde_with::{DeserializeAs, SerializeAs};

use crate::{Timestamp, TimestampExt};

// `serde_with::TimestampSeconds` does not support `u64` or RFC 3339 as `FORMAT`.  (I do not know
// if this is a good idea, but I prefer `u64` over `i64` for timestamps.)
pub struct TimestampSeconds<FORMAT>(PhantomData<FORMAT>);

pub struct Rfc3339;

impl<'de> DeserializeAs<'de, Timestamp> for TimestampSeconds<u64> {
    fn deserialize_as<D>(deserializer: D) -> Result<Timestamp, D::Error>
    where
        D: Deserializer<'de>,
    {
        Timestamp::from_timestamp_secs_u64(Deserialize::deserialize(deserializer)?)
            .map_err(|timestamp| D::Error::custom(format!("invalid timestamp: {timestamp}")))
    }
}

impl SerializeAs<Timestamp> for TimestampSeconds<u64> {
    fn serialize_as<S>(timestamp: &Timestamp, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        timestamp.timestamp_u64().serialize(serializer)
    }
}

impl<'de> DeserializeAs<'de, Timestamp> for TimestampSeconds<Rfc3339> {
    fn deserialize_as<D>(deserializer: D) -> Result<Timestamp, D::Error>
    where
        D: Deserializer<'de>,
    {
        Ok(
            DateTime::parse_from_rfc3339(Deserialize::deserialize(deserializer)?)
                .map_err(D::Error::custom)?
                .with_timezone(&Utc),
        )
    }
}

impl SerializeAs<Timestamp> for TimestampSeconds<Rfc3339> {
    fn serialize_as<S>(timestamp: &Timestamp, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        timestamp
            .to_rfc3339_opts(SecondsFormat::Secs, true)
            .serialize(serializer)
    }
}
