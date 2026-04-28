use std::collections::HashMap;

use reqwest::header::HeaderMap;
use serde::de::{Deserialize, Deserializer, Error as _};
use serde::ser::{Error as _, Serialize, Serializer};

pub(crate) fn deserialize<'de, D>(deserializer: D) -> Result<Option<HeaderMap>, D::Error>
where
    D: Deserializer<'de>,
{
    <Option<HashMap<String, String>>>::deserialize(deserializer)?
        .map(|map| (&map).try_into().map_err(D::Error::custom))
        .transpose()
}

pub(crate) fn serialize<S>(map: &Option<HeaderMap>, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    map.as_ref()
        .map(|map| {
            map.iter()
                .map(|(key, value)| Ok((key.as_str(), value.to_str().map_err(S::Error::custom)?)))
                .try_collect::<HashMap<_, _>>()
        })
        .transpose()?
        .serialize(serializer)
}
