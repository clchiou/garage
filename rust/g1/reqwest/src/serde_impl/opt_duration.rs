use std::time::Duration;

use serde::de::{Deserialize, Deserializer, Error as _};
use serde::ser::{Serialize, Serializer};

use g1_param::parse;
use g1_param::unparse;

pub(crate) fn deserialize<'de, D>(deserializer: D) -> Result<Option<Duration>, D::Error>
where
    D: Deserializer<'de>,
{
    // It seems nice to reuse `g1_param::parse::opt_duration` here.
    parse::opt_duration(<Option<String>>::deserialize(deserializer)?).map_err(D::Error::custom)
}

pub(crate) fn serialize<S>(duration: &Option<Duration>, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    (*duration).map(unparse::duration).serialize(serializer)
}
