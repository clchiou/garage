use serde::de::{Deserialize, Deserializer};
use serde::ser::{Serialize, Serializer};

pub(crate) fn deserialize<'de, T, D>(deserializer: D) -> Result<Option<T>, D::Error>
where
    T: Deserialize<'de>,
    D: Deserializer<'de>,
{
    T::deserialize(deserializer).map(Some)
}

pub(crate) fn serialize<T, S>(option: &Option<T>, serializer: S) -> Result<S::Ok, S::Error>
where
    T: Serialize,
    S: Serializer,
{
    option
        .as_ref()
        .expect("skip_serializing_if = \"Option::is_none\"")
        .serialize(serializer)
}

//
// I thought of exploiting generics to define an `Optional` helper type that could be supplied to
// `serde(with)` when annotating `Option<T>` and `Option<Timestamp>` fields.  Of course, this did
// not work.  Basically, we need a blanket implementation for `T: Deserialize<'de> + Serialize` and
// a specific implementation for `Timestamp`.  However, these two implementations conflict because
// the upstream crate may add a new implementation of `De/Serialize` for `Timestamp`.
//
pub(crate) mod timestamp {
    use std::fmt;

    use serde::de::{self, Deserializer};
    use serde::ser::Serializer;

    use crate::Timestamp;

    pub(crate) fn deserialize<'de, D>(deserializer: D) -> Result<Option<Timestamp>, D::Error>
    where
        D: Deserializer<'de>,
    {
        fn try_from_timestamp<E>(secs: i64) -> Result<Timestamp, E>
        where
            E: de::Error,
        {
            Timestamp::from_timestamp(secs, 0).ok_or_else(|| {
                E::custom(fmt::from_fn(|f| {
                    std::write!(f, "invalid timestamp: {secs}")
                }))
            })
        }

        super::deserialize(deserializer)
            .and_then(|option| option.map(try_from_timestamp).transpose())
    }

    pub(crate) fn serialize<S>(option: &Option<Timestamp>, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        super::serialize(&option.as_ref().map(Timestamp::timestamp), serializer)
    }
}
