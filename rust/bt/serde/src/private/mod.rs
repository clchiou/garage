pub mod optional;

use std::marker::PhantomData;

use serde::de::Deserializer;
use serde::ser::Serializer;

use crate::SerdeWith;

pub struct Optional<SDW>(PhantomData<SDW>);

impl<SDW> Optional<SDW>
where
    SDW: SerdeWith,
{
    pub fn deserialize<'de, D>(deserializer: D) -> Result<Option<SDW::Value>, D::Error>
    where
        D: Deserializer<'de>,
    {
        SDW::deserialize(deserializer).map(Some)
    }

    pub fn serialize<S>(option: &Option<SDW::Value>, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        SDW::serialize(
            option
                .as_ref()
                .expect("skip_serializing_if = \"Option::is_none\""),
            serializer,
        )
    }
}
