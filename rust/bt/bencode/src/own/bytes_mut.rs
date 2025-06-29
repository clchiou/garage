use bytes::BytesMut;

use crate::value;

pub type Value = value::Value<ByteString>;

pub type ByteString = BytesMut;

pub use value::Integer;

pub type List = value::List<ByteString>;
pub type ListIter = value::ListIter<ByteString>;

pub type Dictionary = value::Dictionary<ByteString>;
pub type DictionaryIter = value::DictionaryIter<ByteString>;

impl TryFrom<Value> for ByteString {
    type Error = Value;

    fn try_from(value: Value) -> Result<Self, Self::Error> {
        match value {
            Value::ByteString(bytes) => Ok(bytes),
            _ => Err(value),
        }
    }
}
