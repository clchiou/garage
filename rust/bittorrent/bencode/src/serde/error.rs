use std::fmt;

use serde::{de, ser};
use snafu::prelude::*;

use crate::own::Value;

pub type Result<T> = std::result::Result<T, Error>;

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(visibility(pub(super)))]
pub enum Error {
    #[snafu(display("{message}"))]
    Custom {
        message: String,
    },
    #[snafu(display("decode error: {source:?}"))]
    Decode {
        source: crate::Error,
    },
    #[snafu(display("expect value type {type_name}: {value:?}"))]
    ExpectValueType {
        type_name: &'static str,
        value: Value,
    },
    IntegerValueOutOfRange,
    #[snafu(display("invalid dictionary as enum: {dict:?}"))]
    InvalidDictionaryAsEnum {
        dict: Value,
    },
    #[snafu(display("invalid floating point: {value:?}"))]
    InvalidFloatingPoint {
        value: Vec<u8>,
    },
    #[snafu(display("invalid list as {type_name}: {list:?}"))]
    InvalidListAsType {
        type_name: &'static str,
        list: Value,
    },
    #[snafu(display("invalid utf8 string: \"{string}\""))]
    InvalidUtf8String {
        string: String,
    },
}

impl de::Error for Error {
    fn custom<T: fmt::Display>(message: T) -> Self {
        Error::Custom {
            message: message.to_string(),
        }
    }
}

impl ser::Error for Error {
    fn custom<T: fmt::Display>(message: T) -> Self {
        Error::Custom {
            message: message.to_string(),
        }
    }
}
