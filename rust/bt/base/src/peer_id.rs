use std::array::TryFromSliceError;
use std::borrow::{Borrow, Cow};
use std::fmt;
use std::str::FromStr;
use std::sync::{Arc, LazyLock};

use rand::distr::StandardUniform;
use rand::distr::slice::Choose;
use rand::prelude::*;
use serde::{Deserialize, Deserializer, Serialize, Serializer, de};
use snafu::prelude::*;

use g1_base::slice::ByteSliceExt;

#[derive(Clone, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct PeerId(Arc<[u8; PEER_ID_SIZE]>);

impl fmt::Debug for PeerId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_tuple("PeerId")
            .field_with(|f| std::write!(f, "{}", self.0.escape_ascii()))
            .finish()
    }
}

pub const PEER_ID_SIZE: usize = 20;

//
// NOTE: We deliberately implement `Display` and `FromStr` as inverses of each other.
//

impl fmt::Display for PeerId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        std::write!(f, "{}", self.0.escape_ascii())
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("invalid peer id: {peer_id:?}"))]
pub struct ParsePeerIdError {
    peer_id: String,
}

fn parse(peer_id: Cow<str>) -> Result<PeerId, ParsePeerIdError> {
    let mut id = [0u8; PEER_ID_SIZE];
    let mut bytes = peer_id.as_bytes().unescape_ascii();
    let result: Option<_> = try {
        for ptr in id.iter_mut() {
            *ptr = bytes.next()?.ok()?;
        }
        bytes.next().is_none().then_some(())?
    };
    result.context(ParsePeerIdSnafu { peer_id })?;
    Ok(id.into())
}

impl FromStr for PeerId {
    type Err = ParsePeerIdError;

    fn from_str(peer_id: &str) -> Result<Self, Self::Err> {
        parse(peer_id.into())
    }
}

impl<'de> Deserialize<'de> for PeerId {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        parse(String::deserialize(deserializer)?.into()).map_err(de::Error::custom)
    }
}

impl Serialize for PeerId {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let buffer = &mut [0u8; PEER_ID_SIZE * 4];
        serializer.serialize_str(g1_base::format_str!(buffer, "{self}"))
    }
}

impl Distribution<PeerId> for StandardUniform {
    // TODO: Comply with BEP 20.
    fn sample<R: Rng + ?Sized>(&self, rng: &mut R) -> PeerId {
        static CHARSET: LazyLock<Choose<u8>> = LazyLock::new(|| {
            Choose::new(b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.-")
                .expect("non-empty charset")
        });
        let mut peer_id = [0u8; PEER_ID_SIZE];
        for ptr in peer_id.iter_mut() {
            *ptr = *rng.sample(*CHARSET);
        }
        peer_id.into()
    }
}

impl TryFrom<&[u8]> for PeerId {
    type Error = TryFromSliceError;

    fn try_from(peer_id: &[u8]) -> Result<PeerId, TryFromSliceError> {
        <[u8; PEER_ID_SIZE]>::try_from(peer_id).map(Self::from)
    }
}

impl From<Arc<[u8; PEER_ID_SIZE]>> for PeerId {
    fn from(peer_id: Arc<[u8; PEER_ID_SIZE]>) -> Self {
        Self(peer_id)
    }
}

impl From<[u8; PEER_ID_SIZE]> for PeerId {
    fn from(peer_id: [u8; PEER_ID_SIZE]) -> Self {
        Self(peer_id.into())
    }
}

impl AsRef<[u8; PEER_ID_SIZE]> for PeerId {
    fn as_ref(&self) -> &[u8; PEER_ID_SIZE] {
        self.0.as_ref()
    }
}

impl AsRef<[u8]> for PeerId {
    fn as_ref(&self) -> &[u8] {
        self.0.as_ref()
    }
}

impl Borrow<[u8; PEER_ID_SIZE]> for PeerId {
    fn borrow(&self) -> &[u8; PEER_ID_SIZE] {
        self.0.borrow()
    }
}

impl Borrow<[u8]> for PeerId {
    fn borrow(&self) -> &[u8] {
        self.0.as_slice()
    }
}

#[cfg(test)]
mod tests {
    use std::fmt::Write;

    use hex_literal::hex;
    use serde_json;

    use super::*;

    #[test]
    fn text_format() {
        fn test(testdata: [u8; PEER_ID_SIZE], text: &str) {
            let peer_id = PeerId::from(testdata);

            let mut debug = String::new();
            std::write!(&mut debug, "{peer_id:?}").unwrap();
            assert_eq!(debug, std::format!("PeerId({text})"));

            assert_eq!(text.parse::<PeerId>(), Ok(peer_id.clone()));
            assert_eq!(peer_id.to_string(), text);

            let json = serde_json::to_string(text).unwrap();
            assert_eq!(serde_json::from_str::<PeerId>(&json).unwrap(), peer_id);
            assert_eq!(serde_json::to_string(&peer_id).unwrap(), json);
        }

        test(
            hex!("0000000000000000 0000000000000000 00000000"),
            r#"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"#,
        );
        test(
            hex!("ffffffffffffffff ffffffffffffffff ffffffff"),
            r#"\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff"#,
        );
        test(
            hex!("000102030405060708090a0b0c0d0e0f deadbeef"),
            r#"\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f\xde\xad\xbe\xef"#,
        );
        test(*b"01234567890123456789", "01234567890123456789");
        test(*b"!@#$%^&*() ghijklm-.", "!@#$%^&*() ghijklm-.");

        for testdata in [
            "",
            "0123456789012345678",
            "012345678901234567890",
            "\x001234567890123456789",
        ] {
            assert_eq!(
                testdata.parse::<PeerId>(),
                Err(ParsePeerIdError {
                    peer_id: testdata.to_string(),
                }),
            );
        }

        let peer_id = rand::random::<PeerId>();
        let json = serde_json::to_string(&peer_id).unwrap();
        assert_eq!(serde_json::from_str::<PeerId>(&json).unwrap(), peer_id);
    }
}
