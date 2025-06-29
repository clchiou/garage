use std::fmt;
use std::io;

use snafu::prelude::*;

#[derive(Debug, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    #[snafu(display("bencode error: {source}"))]
    Bencode { source: super::Error },
    #[snafu(display("bencode io error: {source}"))]
    Io { source: io::Error },
}

impl From<super::Error> for Error {
    fn from(source: super::Error) -> Self {
        Self::Bencode { source }
    }
}

impl serde::de::Error for Error {
    fn custom<T>(message: T) -> Self
    where
        T: fmt::Display,
    {
        Error::Bencode {
            source: super::Error::custom(message),
        }
    }
}

impl serde::ser::Error for Error {
    fn custom<T>(message: T) -> Self
    where
        T: fmt::Display,
    {
        Error::Bencode {
            source: super::Error::custom(message),
        }
    }
}

impl super::de::Error for Error {
    fn is_eof(&self) -> bool {
        self.to_bencode().is_some_and(super::Error::is_eof)
    }

    fn is_incomplete(&self) -> bool {
        self.to_bencode().is_some_and(super::Error::is_incomplete)
    }

    fn is_strict(&self) -> bool {
        self.to_bencode().is_some_and(super::Error::is_strict)
    }
}

impl Error {
    fn to_bencode(&self) -> Option<&super::Error> {
        match self {
            Self::Bencode { source } => Some(source),
            _ => None,
        }
    }
}
