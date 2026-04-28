use reqwest::header::HeaderValue;

use serde::de::{Deserialize, Deserializer, Error as _};
use serde::ser::{Error as _, Serialize, Serializer};

pub(crate) fn deserialize<'de, D>(deserializer: D) -> Result<Option<HeaderValue>, D::Error>
where
    D: Deserializer<'de>,
{
    <Option<String>>::deserialize(deserializer)?
        .map(|value| value.try_into().map_err(D::Error::custom))
        .transpose()
}

pub(crate) fn serialize<S>(value: &Option<HeaderValue>, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    value
        .as_ref()
        .map(|value| value.to_str().map_err(S::Error::custom))
        .transpose()?
        .serialize(serializer)
}
