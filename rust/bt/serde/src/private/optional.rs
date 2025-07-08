use serde::de::{Deserialize, Deserializer};
use serde::ser::{Serialize, Serializer};

pub fn deserialize<'de, T, D>(deserializer: D) -> Result<Option<T>, D::Error>
where
    T: Deserialize<'de>,
    D: Deserializer<'de>,
{
    T::deserialize(deserializer).map(Some)
}

pub fn serialize<T, S>(option: &Option<T>, serializer: S) -> Result<S::Ok, S::Error>
where
    T: Serialize,
    S: Serializer,
{
    option
        .as_ref()
        .expect("skip_serializing_if = \"Option::is_none\"")
        .serialize(serializer)
}
