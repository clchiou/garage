use std::array::TryFromSliceError;
use std::borrow::{Borrow, Cow};
use std::fmt;
use std::str::FromStr;
use std::sync::Arc;

use serde::{Deserialize, Deserializer, Serialize, Serializer, de};
use snafu::prelude::*;

use g1_base::fmt::{DebugExt, Hex};
use g1_base::str;

#[derive(Clone, DebugExt, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct InfoHash(#[debug(with = Hex)] Arc<[u8; INFO_HASH_SIZE]>);

pub const INFO_HASH_SIZE: usize = 20;

//
// NOTE: We deliberately implement `Display` and `FromStr` as inverses of each other.
//

impl fmt::Display for InfoHash {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        std::write!(f, "{:?}", Hex(&self.0))
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("invalid info hash: {info_hash:?}"))]
pub struct ParseInfoHashError {
    info_hash: String,
}

fn parse(info_hash: Cow<str>) -> Result<InfoHash, ParseInfoHashError> {
    match str::Hex::try_from(&*info_hash) {
        Ok(str::Hex(info_hash)) => Ok(info_hash.into()),
        Err(_) => Err(ParseInfoHashError {
            info_hash: info_hash.into_owned(),
        }),
    }
}

impl FromStr for InfoHash {
    type Err = ParseInfoHashError;

    fn from_str(info_hash: &str) -> Result<Self, Self::Err> {
        parse(info_hash.into())
    }
}

impl<'de> Deserialize<'de> for InfoHash {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        parse(String::deserialize(deserializer)?.into()).map_err(de::Error::custom)
    }
}

impl Serialize for InfoHash {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let buffer = &mut [0u8; INFO_HASH_SIZE * 2];
        serializer.serialize_str(g1_base::format_str!(buffer, "{self}"))
    }
}

impl TryFrom<&[u8]> for InfoHash {
    type Error = TryFromSliceError;

    fn try_from(info_hash: &[u8]) -> Result<Self, Self::Error> {
        <[u8; INFO_HASH_SIZE]>::try_from(info_hash).map(Self::from)
    }
}

impl From<Arc<[u8; INFO_HASH_SIZE]>> for InfoHash {
    fn from(info_hash: Arc<[u8; INFO_HASH_SIZE]>) -> Self {
        Self(info_hash)
    }
}

impl From<[u8; INFO_HASH_SIZE]> for InfoHash {
    fn from(info_hash: [u8; INFO_HASH_SIZE]) -> Self {
        Self(info_hash.into())
    }
}

impl AsRef<[u8; INFO_HASH_SIZE]> for InfoHash {
    fn as_ref(&self) -> &[u8; INFO_HASH_SIZE] {
        self.0.as_ref()
    }
}

impl AsRef<[u8]> for InfoHash {
    fn as_ref(&self) -> &[u8] {
        self.0.as_ref()
    }
}

impl Borrow<[u8; INFO_HASH_SIZE]> for InfoHash {
    fn borrow(&self) -> &[u8; INFO_HASH_SIZE] {
        self.0.borrow()
    }
}

impl Borrow<[u8]> for InfoHash {
    fn borrow(&self) -> &[u8] {
        self.0.as_slice()
    }
}

#[cfg(test)]
mod tests {
    use std::fmt::Write;

    use hex_literal::hex;
    use serde_json;

    use g1_base::str::StrExt;

    use super::*;

    #[test]
    fn text_format() {
        fn test(testdata: [u8; INFO_HASH_SIZE], text: &str) {
            let info_hash = InfoHash::from(testdata);

            let mut debug = String::new();
            std::write!(&mut debug, "{info_hash:?}").unwrap();
            assert_eq!(debug, std::format!("InfoHash({text})"));

            assert_eq!(text.parse::<InfoHash>(), Ok(info_hash.clone()));
            assert_eq!(
                to_upper(text, &mut [0u8; 64]).parse::<InfoHash>(),
                Ok(info_hash.clone()),
            );
            assert_eq!(info_hash.to_string(), text);

            let json = serde_json::to_string(text).unwrap();
            assert_eq!(serde_json::from_str::<InfoHash>(&json).unwrap(), info_hash);
            assert_eq!(serde_json::to_string(&info_hash).unwrap(), json);
        }

        fn to_upper<'a>(text: &str, buffer: &'a mut [u8]) -> &'a str {
            text.transform(buffer, |x| {
                x.make_ascii_uppercase();
                Some(&*x)
            })
            .unwrap()
        }

        test(
            hex!("000102030405060708090a0b0c0d0e0f deadbeef"),
            "000102030405060708090a0b0c0d0e0fdeadbeef",
        );

        for testdata in [
            "",
            "000102030405060708090a0b0c0d0e0fDEADBEE",
            "000102030405060708090a0b0c0d0e0fDEADBEEF0",
            "XYZ102030405060708090a0b0c0d0e0fDEADBEEF",
        ] {
            assert_eq!(
                testdata.parse::<InfoHash>(),
                Err(ParseInfoHashError {
                    info_hash: testdata.to_string(),
                }),
            );
        }
    }
}
