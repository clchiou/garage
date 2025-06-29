pub mod de;
pub mod io;
pub mod ser;

use std::fmt;

use bytes::Bytes;
use snafu::prelude::*;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    //
    // Bencode errors.
    //

    // `Eof` (empty input) is a special case of `Incomplete` (partial input).  I hope the benefits
    // justify the added complexity of distinguishing between the two error types.
    #[snafu(display("end of file"))]
    Eof,
    #[snafu(display("incomplete bencode data"))]
    Incomplete,

    #[snafu(display("unknown prefix character: '{}'", prefix.escape_ascii()))]
    Prefix { prefix: u8 },

    #[snafu(display("byte string size limit exceeded: {size}"))]
    ByteStringSizeExceeded { size: usize },

    // BEP 3 specifies that integers have unlimited precision, but we do not support this for
    // practical reasons.
    #[snafu(display("integer buffer overflow: {buffer:?}"))]
    IntegerBufferOverflow { buffer: Bytes },
    #[snafu(display("invalid integer: {integer:?}"))]
    Integer { integer: Bytes },
    #[snafu(display("{int_type_name} overflow: {integer:?}"))]
    IntegerOverflow {
        int_type_name: &'static str,
        integer: Bytes,
    },

    #[snafu(display("expect byte string dictionary key: {type_name}"))]
    KeyType { type_name: &'static str },
    #[snafu(display("missing dictionary value: {key:?}"))]
    MissingValue { key: Bytes },

    //
    // Strict Bencode errors.
    //
    #[snafu(display("expect strict integer: {integer:?}"))]
    StrictInteger { integer: Bytes },
    #[snafu(display("expect strictly increasing dictionary keys: {last_key:?} >= {key:?}"))]
    StrictDictionaryKey { last_key: Bytes, key: Bytes },

    //
    // `de` and `ser` errors.
    //
    #[snafu(display("{message}"))]
    Custom { message: String },
}

impl self::de::Error for Error {
    fn is_eof(&self) -> bool {
        self == &Error::Eof
    }

    fn is_incomplete(&self) -> bool {
        self == &Error::Incomplete
    }

    fn is_strict(&self) -> bool {
        matches!(
            self,
            Error::StrictInteger { .. } | Error::StrictDictionaryKey { .. },
        )
    }
}

impl serde::de::Error for Error {
    fn custom<T>(message: T) -> Self
    where
        T: fmt::Display,
    {
        Error::Custom {
            message: message.to_string(),
        }
    }
}

impl serde::ser::Error for Error {
    fn custom<T>(message: T) -> Self
    where
        T: fmt::Display,
    {
        Error::Custom {
            message: message.to_string(),
        }
    }
}
