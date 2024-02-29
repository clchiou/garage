use snafu::prelude::*;

use bittorrent_base::{INFO_HASH_SIZE, NODE_ID_SIZE};
use bittorrent_bencode::{
    borrow,
    convert::{self, to_bytes},
    dict,
};

use crate::message::{Error, ExpectIdSizeSnafu, ExpectInfoHashSizeSnafu};

impl From<convert::Error> for Error {
    fn from(error: convert::Error) -> Self {
        match error {
            convert::Error::ExpectByteString { value } => Self::ExpectByteString { value },
            convert::Error::ExpectInteger { value } => Self::ExpectInteger { value },
            convert::Error::ExpectList { value } => Self::ExpectList { value },
            convert::Error::ExpectDictionary { value } => Self::ExpectDictionary { value },
            convert::Error::InvalidUtf8String { string } => Self::InvalidUtf8String { string },
        }
    }
}

impl From<dict::Error> for Error {
    fn from(error: dict::Error) -> Self {
        match error {
            dict::Error::MissingDictionaryKey { key } => Error::MissingDictionaryKey { key },
        }
    }
}

pub(super) fn to_id(value: borrow::Value) -> Result<&'_ [u8], Error> {
    to_bytes(value).and_then(|id| {
        ensure!(
            id.len() == NODE_ID_SIZE,
            ExpectIdSizeSnafu { id: id.to_vec() },
        );
        Ok(id)
    })
}

pub(super) fn to_info_hash(value: borrow::Value) -> Result<&'_ [u8], Error> {
    to_bytes(value).and_then(|info_hash| {
        ensure!(
            info_hash.len() == INFO_HASH_SIZE,
            ExpectInfoHashSizeSnafu {
                info_hash: info_hash.to_vec(),
            },
        );
        Ok(info_hash)
    })
}

#[cfg(test)]
mod tests {
    use super::{super::test_harness::*, *};

    #[test]
    fn id() {
        assert_eq!(
            to_id(new_bytes(b"0123456789012345678")),
            Err(Error::ExpectIdSize {
                id: b"0123456789012345678".to_vec(),
            }),
        );
        assert_eq!(
            to_id(new_bytes(b"012345678901234567890")),
            Err(Error::ExpectIdSize {
                id: b"012345678901234567890".to_vec(),
            }),
        );
    }

    #[test]
    fn info_hash() {
        assert_eq!(
            to_info_hash(new_bytes(b"0123456789012345678")),
            Err(Error::ExpectInfoHashSize {
                info_hash: b"0123456789012345678".to_vec(),
            }),
        );
        assert_eq!(
            to_info_hash(new_bytes(b"012345678901234567890")),
            Err(Error::ExpectInfoHashSize {
                info_hash: b"012345678901234567890".to_vec(),
            }),
        );
    }
}
