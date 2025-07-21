use std::array::TryFromSliceError;
use std::borrow::{Borrow, Cow};
use std::fmt;
use std::str::FromStr;
use std::sync::Arc;

use bitvec::prelude::*;
use rand::distr::StandardUniform;
use rand::prelude::*;
use serde::{Deserialize, Deserializer, Serialize, Serializer, de};
use snafu::prelude::*;

use g1_base::fmt::{DebugExt, Hex};
use g1_base::str;

use crate::info_hash::InfoHash;

//
// Implementer's Notes: BEP 5 does not appear to specify which endianness should be used to
// interpret the node id or info hash as a 160-bit integer.  For now, I assume it is network endian
// (big endian).  Note that big endian (most significant *byte* first) is not the same as `Msb0`
// (most significant *bit* first), but I believe this difference should not matter in practice.
//

#[derive(Clone, DebugExt, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct NodeId(#[debug(with = Hex)] Arc<[u8; NODE_ID_SIZE]>);

pub type NodeIdBitSlice = BitSlice<u8, Msb0>;

pub type NodeDistance = BitArr!(for NODE_ID_BIT_SIZE, in u8, Msb0);

pub const NODE_ID_SIZE: usize = 20;
pub const NODE_ID_BIT_SIZE: usize = NODE_ID_SIZE * 8;

//
// NOTE: We deliberately implement `Display` and `FromStr` as inverses of each other.
//

impl fmt::Display for NodeId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        std::write!(f, "{:?}", Hex(&self.0))
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(display("invalid node id: {node_id:?}"))]
pub struct ParseNodeIdError {
    node_id: String,
}

fn parse(node_id: Cow<str>) -> Result<NodeId, ParseNodeIdError> {
    match str::Hex::try_from(&*node_id) {
        Ok(str::Hex(node_id)) => Ok(node_id.into()),
        Err(_) => Err(ParseNodeIdError {
            node_id: node_id.into_owned(),
        }),
    }
}

impl FromStr for NodeId {
    type Err = ParseNodeIdError;

    fn from_str(node_id: &str) -> Result<Self, Self::Err> {
        parse(node_id.into())
    }
}

impl<'de> Deserialize<'de> for NodeId {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        parse(String::deserialize(deserializer)?.into()).map_err(de::Error::custom)
    }
}

impl Serialize for NodeId {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let buffer = &mut [0u8; NODE_ID_SIZE * 2];
        serializer.serialize_str(g1_base::format_str!(buffer, "{self}"))
    }
}

impl Distribution<NodeId> for StandardUniform {
    fn sample<R: Rng + ?Sized>(&self, rng: &mut R) -> NodeId {
        let mut node_id = [0u8; NODE_ID_SIZE];
        rng.fill(&mut node_id);
        node_id.into()
    }
}

impl TryFrom<&[u8]> for NodeId {
    type Error = TryFromSliceError;

    fn try_from(node_id: &[u8]) -> Result<Self, Self::Error> {
        <[u8; NODE_ID_SIZE]>::try_from(node_id).map(Self::from)
    }
}

impl From<Arc<[u8; NODE_ID_SIZE]>> for NodeId {
    fn from(node_id: Arc<[u8; NODE_ID_SIZE]>) -> Self {
        Self(node_id)
    }
}

impl From<[u8; NODE_ID_SIZE]> for NodeId {
    fn from(node_id: [u8; NODE_ID_SIZE]) -> Self {
        Self(node_id.into())
    }
}

impl AsRef<[u8; NODE_ID_SIZE]> for NodeId {
    fn as_ref(&self) -> &[u8; NODE_ID_SIZE] {
        self.0.as_ref()
    }
}

impl AsRef<[u8]> for NodeId {
    fn as_ref(&self) -> &[u8] {
        self.0.as_ref()
    }
}

impl Borrow<[u8; NODE_ID_SIZE]> for NodeId {
    fn borrow(&self) -> &[u8; NODE_ID_SIZE] {
        self.0.borrow()
    }
}

impl Borrow<[u8]> for NodeId {
    fn borrow(&self) -> &[u8] {
        self.0.as_slice()
    }
}

impl NodeId {
    pub fn pretend(InfoHash(bytes): InfoHash) -> Self {
        Self(bytes)
    }

    pub fn bits(&self) -> &NodeIdBitSlice {
        self.0.view_bits()
    }

    pub fn distance(&self, rhs: &Self) -> NodeDistance {
        let mut distance = NodeDistance::new(*self.0);
        distance ^= rhs.bits();
        distance
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
        fn test(testdata: [u8; NODE_ID_SIZE], text: &str) {
            let node_id = NodeId::from(testdata);

            let mut debug = String::new();
            std::write!(&mut debug, "{node_id:?}").unwrap();
            assert_eq!(debug, std::format!("NodeId({text})"));

            assert_eq!(text.parse::<NodeId>(), Ok(node_id.clone()));
            assert_eq!(
                to_upper(text, &mut [0u8; 64]).parse::<NodeId>(),
                Ok(node_id.clone()),
            );
            assert_eq!(node_id.to_string(), text);

            let json = serde_json::to_string(text).unwrap();
            assert_eq!(serde_json::from_str::<NodeId>(&json).unwrap(), node_id);
            assert_eq!(serde_json::to_string(&node_id).unwrap(), json);
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
                testdata.parse::<NodeId>(),
                Err(ParseNodeIdError {
                    node_id: testdata.to_string(),
                }),
            );
        }

        let node_id = rand::random::<NodeId>();
        let json = serde_json::to_string(&node_id).unwrap();
        assert_eq!(serde_json::from_str::<NodeId>(&json).unwrap(), node_id);
    }

    #[test]
    fn distance() {
        fn test(p: [u8; NODE_ID_SIZE], q: [u8; NODE_ID_SIZE], expect: [u8; NODE_ID_SIZE]) {
            let p = NodeId::from(p);
            let q = NodeId::from(q);
            let expect = NodeDistance::new(expect);
            assert_eq!(p.distance(&q), expect);
            assert_eq!(q.distance(&p), expect);
        }

        test(
            hex!("0000000000000000 0123456789abcdef 00000000"),
            hex!("0123456789abcdef 0123456789abcdef deadbeef"),
            hex!("0123456789abcdef 0000000000000000 deadbeef"),
        );
    }
}
