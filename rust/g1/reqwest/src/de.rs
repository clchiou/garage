use std::collections::HashMap;
use std::time::Duration;

use regex::Regex;
use reqwest::header::{HeaderMap, HeaderValue};

use serde::de::{Deserializer, Error};
use serde::Deserialize;

use g1_param::parse;

pub(crate) fn opt_duration<'de, D>(deserializer: D) -> Result<Option<Duration>, D::Error>
where
    D: Deserializer<'de>,
{
    // It seems nice to reuse `g1_param::parse::opt_duration` here.
    parse::opt_duration(<Option<String>>::deserialize(deserializer)?).map_err(D::Error::custom)
}

pub(crate) fn opt_header_map<'de, D>(deserializer: D) -> Result<Option<HeaderMap>, D::Error>
where
    D: Deserializer<'de>,
{
    <Option<HashMap<String, String>>>::deserialize(deserializer)?
        .map(|map| (&map).try_into().map_err(D::Error::custom))
        .transpose()
}

pub(crate) fn opt_header_value<'de, D>(deserializer: D) -> Result<Option<HeaderValue>, D::Error>
where
    D: Deserializer<'de>,
{
    <Option<String>>::deserialize(deserializer)?
        .map(|value| value.try_into().map_err(D::Error::custom))
        .transpose()
}

pub(crate) fn regex<'de, D>(deserializer: D) -> Result<Regex, D::Error>
where
    D: Deserializer<'de>,
{
    Regex::new(&String::deserialize(deserializer)?).map_err(D::Error::custom)
}
