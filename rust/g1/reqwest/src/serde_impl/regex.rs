use std::sync::Arc;

use regex::Regex;
use serde::de::{Deserialize, Deserializer, Error as _};
use serde::ser::{Serialize, Serializer};

pub(crate) type RegexTuple = (Arc<str>, Regex);

pub(crate) fn deserialize<'de, D>(deserializer: D) -> Result<RegexTuple, D::Error>
where
    D: Deserializer<'de>,
{
    let regex_lit = <Arc<str>>::deserialize(deserializer)?;
    let regex = Regex::new(&regex_lit).map_err(D::Error::custom)?;
    Ok((regex_lit, regex))
}

pub(crate) fn serialize<S>((regex_lit, _): &RegexTuple, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    regex_lit.serialize(serializer)
}
