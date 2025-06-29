use crate::raw;
use crate::value;

pub type Value<'a> = value::Value<ByteString<'a>>;

pub type ByteString<'a> = &'a [u8];

pub use value::Integer;

pub type List<'a> = value::List<ByteString<'a>>;
pub type ListIter<'a> = value::ListIter<ByteString<'a>>;

pub type Dictionary<'a> = value::Dictionary<ByteString<'a>>;
pub type DictionaryIter<'a> = value::DictionaryIter<ByteString<'a>>;

pub type WithRaw<'a, T> = raw::WithRaw<T, &'a [u8]>;

impl<'a> TryFrom<Value<'a>> for ByteString<'a> {
    type Error = Value<'a>;

    fn try_from(value: Value<'a>) -> Result<Self, Self::Error> {
        match value {
            Value::ByteString(bytes) => Ok(bytes),
            _ => Err(value),
        }
    }
}
