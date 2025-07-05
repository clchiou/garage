use std::array::TryFromSliceError;
use std::borrow::{Borrow, Cow};
use std::fmt;
use std::str::FromStr;
use std::sync::Arc;

use serde::{Deserialize, Deserializer, Serialize, Serializer, de};
use snafu::prelude::*;

use g1_base::fmt::{DebugExt, Hex};
use g1_base::str;

// BEPs do not specify this, but some BitTorrent implementations include it.
#[derive(Clone, DebugExt, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct Md5Hash(#[debug(with = Hex)] Arc<[u8; MD5_HASH_SIZE]>);

pub const MD5_HASH_SIZE: usize = 16;

//
// NOTE: We deliberately implement `Display` and `FromStr` as inverses of each other.
//

impl fmt::Display for Md5Hash {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        std::write!(f, "{:?}", Hex(&self.0))
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("invalid md5 hash: {md5_hash:?}"))]
pub struct ParseMd5HashError {
    md5_hash: String,
}

fn parse(md5_hash: Cow<str>) -> Result<Md5Hash, ParseMd5HashError> {
    match str::Hex::try_from(&*md5_hash) {
        Ok(str::Hex(md5_hash)) => Ok(md5_hash.into()),
        Err(_) => Err(ParseMd5HashError {
            md5_hash: md5_hash.into_owned(),
        }),
    }
}

impl FromStr for Md5Hash {
    type Err = ParseMd5HashError;

    fn from_str(md5_hash: &str) -> Result<Self, Self::Err> {
        parse(md5_hash.into())
    }
}

impl<'de> Deserialize<'de> for Md5Hash {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        parse(String::deserialize(deserializer)?.into()).map_err(de::Error::custom)
    }
}

impl Serialize for Md5Hash {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let buffer = &mut [0u8; MD5_HASH_SIZE * 2];
        serializer.serialize_str(g1_base::format_str!(buffer, "{self}"))
    }
}

impl TryFrom<&[u8]> for Md5Hash {
    type Error = TryFromSliceError;

    fn try_from(md5_hash: &[u8]) -> Result<Self, Self::Error> {
        <[u8; MD5_HASH_SIZE]>::try_from(md5_hash).map(Self::from)
    }
}

impl From<Arc<[u8; MD5_HASH_SIZE]>> for Md5Hash {
    fn from(md5_hash: Arc<[u8; MD5_HASH_SIZE]>) -> Self {
        Self(md5_hash)
    }
}

impl From<[u8; MD5_HASH_SIZE]> for Md5Hash {
    fn from(md5_hash: [u8; MD5_HASH_SIZE]) -> Self {
        Self(md5_hash.into())
    }
}

impl AsRef<[u8; MD5_HASH_SIZE]> for Md5Hash {
    fn as_ref(&self) -> &[u8; MD5_HASH_SIZE] {
        self.0.as_ref()
    }
}

impl AsRef<[u8]> for Md5Hash {
    fn as_ref(&self) -> &[u8] {
        self.0.as_ref()
    }
}

impl Borrow<[u8; MD5_HASH_SIZE]> for Md5Hash {
    fn borrow(&self) -> &[u8; MD5_HASH_SIZE] {
        self.0.borrow()
    }
}

impl Borrow<[u8]> for Md5Hash {
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
        fn test(testdata: [u8; MD5_HASH_SIZE], text: &str) {
            let md5_hash = Md5Hash::from(testdata);

            let mut debug = String::new();
            std::write!(&mut debug, "{md5_hash:?}").unwrap();
            assert_eq!(debug, std::format!("Md5Hash({text})"));

            assert_eq!(text.parse::<Md5Hash>(), Ok(md5_hash.clone()));
            assert_eq!(
                to_upper(text, &mut [0u8; 64]).parse::<Md5Hash>(),
                Ok(md5_hash.clone()),
            );
            assert_eq!(md5_hash.to_string(), text);

            let json = serde_json::to_string(text).unwrap();
            assert_eq!(serde_json::from_str::<Md5Hash>(&json).unwrap(), md5_hash);
            assert_eq!(serde_json::to_string(&md5_hash).unwrap(), json);
        }

        fn to_upper<'a>(text: &str, buffer: &'a mut [u8]) -> &'a str {
            text.transform(buffer, |x| {
                x.make_ascii_uppercase();
                Some(&*x)
            })
            .unwrap()
        }

        test(
            hex!("000102030405060708090a0b0c0d0e0f"),
            "000102030405060708090a0b0c0d0e0f",
        );

        for testdata in [
            "",
            "000102030405060708090a0b0c0d0e0",
            "000102030405060708090a0b0c0d0e0f0",
            "XYZ102030405060708090a0b0c0d0e0f",
        ] {
            assert_eq!(
                testdata.parse::<Md5Hash>(),
                Err(ParseMd5HashError {
                    md5_hash: testdata.to_string(),
                }),
            );
        }
    }
}
