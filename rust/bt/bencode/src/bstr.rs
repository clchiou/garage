use bytes::{Bytes, BytesMut};
use serde::de;

pub trait OwnedBStr: AsRef<[u8]> + Ord + Sized {
    //
    // Converts `OwnedBStr` to and from Serde byte string.
    //

    fn from_bytes(bytes: &[u8]) -> Self;

    fn from_static_bytes(bytes: &'static [u8]) -> Self {
        Self::from_bytes(bytes)
    }

    fn from_byte_buf(bytes: Vec<u8>) -> Self;

    fn into_byte_buf(self) -> Vec<u8>;
}

impl OwnedBStr for Bytes {
    fn from_bytes(bytes: &[u8]) -> Self {
        Bytes::copy_from_slice(bytes)
    }

    fn from_static_bytes(bytes: &'static [u8]) -> Self {
        Bytes::from_static(bytes)
    }

    fn from_byte_buf(bytes: Vec<u8>) -> Self {
        bytes.into()
    }

    fn into_byte_buf(self) -> Vec<u8> {
        self.into()
    }
}

impl OwnedBStr for BytesMut {
    fn from_bytes(bytes: &[u8]) -> Self {
        bytes.into()
    }

    fn from_byte_buf(bytes: Vec<u8>) -> Self {
        Bytes::from(bytes).into()
    }

    fn into_byte_buf(self) -> Vec<u8> {
        self.into()
    }
}

impl OwnedBStr for Vec<u8> {
    fn from_bytes(bytes: &[u8]) -> Self {
        bytes.into()
    }

    fn from_byte_buf(bytes: Vec<u8>) -> Self {
        bytes
    }

    fn into_byte_buf(self) -> Vec<u8> {
        self
    }
}

pub trait DeserializableBStr<'de>: AsRef<[u8]> + Ord + Sized {
    //
    // Converts `DeserializableBStr` from Serde byte string.
    //

    fn from_bytes<E>(value: &[u8]) -> Result<Self, E>
    where
        E: de::Error;

    fn from_byte_buf<E>(value: Vec<u8>) -> Result<Self, E>
    where
        E: de::Error;

    fn from_borrowed_bytes<E>(value: &'de [u8]) -> Result<Self, E>
    where
        E: de::Error;

    // Invokes either `visit_byte_buf` or `visit_borrowed_bytes`.
    fn apply_visit_bytes<V, E>(self, visitor: V) -> Result<V::Value, E>
    where
        V: de::Visitor<'de>,
        E: de::Error;
}

// TODO: I tried adding `BorrowedBStr` with blanket implementations like this:
// ```
// impl<B> DeserializableBStr for B where B: OwnedBStr { ... }
// impl<B> DeserializableBStr for B where B: BorrowedBStr { ... }
// ```
// However, these implementations conflict, and I could not resolve the issue, even with negative
// trait bounds.
impl<'de, B> DeserializableBStr<'de> for B
where
    B: OwnedBStr,
{
    fn from_bytes<E>(value: &[u8]) -> Result<Self, E>
    where
        E: de::Error,
    {
        Ok(Self::from_bytes(value))
    }

    fn from_byte_buf<E>(value: Vec<u8>) -> Result<Self, E>
    where
        E: de::Error,
    {
        Ok(Self::from_byte_buf(value))
    }

    fn from_borrowed_bytes<E>(value: &'de [u8]) -> Result<Self, E>
    where
        E: de::Error,
    {
        Ok(Self::from_bytes(value))
    }

    fn apply_visit_bytes<V, E>(self, visitor: V) -> Result<V::Value, E>
    where
        V: de::Visitor<'de>,
        E: de::Error,
    {
        visitor.visit_byte_buf(self.into_byte_buf())
    }
}

impl<'de> DeserializableBStr<'de> for &'de [u8] {
    fn from_bytes<E>(value: &[u8]) -> Result<Self, E>
    where
        E: de::Error,
    {
        Err(E::custom(std::format!(
            "borrow from transient byte string: b\"{}\"",
            value.escape_ascii(),
        )))
    }

    fn from_byte_buf<E>(value: Vec<u8>) -> Result<Self, E>
    where
        E: de::Error,
    {
        Err(E::custom(std::format!(
            "borrow from owned byte string: b\"{}\"",
            value.escape_ascii(),
        )))
    }

    fn from_borrowed_bytes<E>(value: &'de [u8]) -> Result<Self, E>
    where
        E: de::Error,
    {
        Ok(value)
    }

    fn apply_visit_bytes<V, E>(self, visitor: V) -> Result<V::Value, E>
    where
        V: de::Visitor<'de>,
        E: de::Error,
    {
        visitor.visit_borrowed_bytes(self)
    }
}
