use std::array::TryFromSliceError;
use std::borrow::{Borrow, Cow};
use std::fmt;
use std::str::FromStr;
use std::sync::{Arc, LazyLock};

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
        rng.random::<[u8; NODE_ID_SIZE]>().into()
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

// I am not sure if this is a good idea, but adding a zero default value seems quite useful.
impl Default for NodeId {
    fn default() -> Self {
        static ZERO: LazyLock<NodeId> = LazyLock::new(|| [0; NODE_ID_SIZE].into());
        ZERO.clone()
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

    /// Returns a new id, where the bits `0..bit_index` are copied from the original, bit
    /// `bit_index` is inverted, and the bits `bit_index + 1..` are random.
    pub fn invert_then_random_suffix(&self, bit_index: usize) -> Self {
        let mut id = *self.0;
        if bit_index < NODE_ID_BIT_SIZE {
            let id = NodeIdBitSlice::from_slice_mut(&mut id);

            id.set(bit_index, !id[bit_index]);

            if bit_index + 1 < NODE_ID_BIT_SIZE {
                let random_id = rand::random::<[u8; NODE_ID_SIZE]>();
                let random_id = NodeIdBitSlice::from_slice(&random_id);
                id[bit_index + 1..].copy_from_bitslice(&random_id[bit_index + 1..]);
            }
        }
        id.into()
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

    #[test]
    fn invert_then_random_suffix() {
        const N: usize = 30;

        fn test(id: NodeId, bit_index: usize) {
            let mut suffix_eq_count = 0;
            for _ in 0..N {
                let actual = id.invert_then_random_suffix(bit_index);
                let actual = NodeIdBitSlice::from_slice(&*actual.0);
                let expect = NodeIdBitSlice::from_slice(&*id.0);

                assert_eq!(&actual[..bit_index], &expect[..bit_index]);
                assert_ne!(actual[bit_index], expect[bit_index]);

                if &actual[bit_index + 1..] == &expect[bit_index + 1..] {
                    suffix_eq_count += 1;
                }
            }
            // When `bit_index + 1 == NODE_ID_BIT_SIZE - 1`, the probability that
            // `suffix_eq_count == N` is `1 / 2**N`, which should be sufficiently low.
            assert!(suffix_eq_count < N);
        }

        let x00 = NodeId::from([0x00; 20]);
        let xff = NodeId::from([0xff; 20]);
        for bit_index in [0, 1, 2, 3, 8, 11, 23, 63, 64, 65, 157, 158] {
            test(x00.clone(), bit_index);
            test(xff.clone(), bit_index);
        }

        let x00_inv = NodeId::from(hex!("0000000000000000 0000000000000000 00000001"));
        let xff_inv = NodeId::from(hex!("ffffffffffffffff ffffffffffffffff fffffffe"));
        for _ in 0..N {
            assert_eq!(x00.invert_then_random_suffix(159), x00_inv);
            assert_eq!(xff.invert_then_random_suffix(159), xff_inv);
            assert_eq!(x00.invert_then_random_suffix(160), x00);
            assert_eq!(xff.invert_then_random_suffix(160), xff);
        }
    }
}
