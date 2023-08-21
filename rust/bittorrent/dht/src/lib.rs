//! Distributed Hash Table
// TODO: Implement BEP 32 IPv6 extension for DHT.

#![feature(iterator_try_collect)]
#![cfg_attr(test, feature(generic_arg_infer))]

mod message;

use std::array::TryFromSliceError;
use std::net::SocketAddr;
use std::sync::Arc;

use bitvec::prelude::*;
use serde::{de, Deserialize, Deserializer};

use g1_base::fmt::{DebugExt, Hex};

use bittorrent_base::{INFO_HASH_SIZE, NODE_ID_SIZE};

// Our code is written under this assumption.
#[allow(clippy::assertions_on_constants)]
const _: () = assert!(INFO_HASH_SIZE == NODE_ID_SIZE);

#[derive(Clone, DebugExt, Deserialize, Eq, Hash, PartialEq)]
pub struct NodeId(
    #[debug(with = Hex)]
    #[serde(deserialize_with = "parse_arc_node_id")]
    Arc<[u8; NODE_ID_SIZE]>,
);

// BEP 5 does not seem to specify which endianness should be used to interpret the node id or info
// hash as a 160-bit integer.  For now, I assume it is network endian (big endian).  Note that big
// endian (most significant *byte* first) is not the same as `Msb0` (most significant *bit* first),
// but I think this difference should not matter in practice.
pub(crate) type NodeIdBitArr = BitArr!(for NODE_ID_BIT_SIZE, in u8, Msb0);
pub(crate) type NodeIdBitSlice = BitSlice<u8, Msb0>;

pub(crate) const NODE_ID_BIT_SIZE: usize = NODE_ID_SIZE * 8;

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
pub struct NodeContactInfo {
    pub id: NodeId,
    pub endpoint: SocketAddr,
}

#[derive(Clone, DebugExt, Eq, Ord, PartialEq, PartialOrd)]
pub(crate) struct Distance(#[debug(with = format_node_id_bit_arr)] NodeIdBitArr);

impl<'a> TryFrom<&'a [u8]> for NodeId {
    type Error = TryFromSliceError;

    fn try_from(node_id: &'a [u8]) -> Result<NodeId, TryFromSliceError> {
        node_id.try_into().map(NodeId::new)
    }
}

impl NodeId {
    pub fn new(node_id: [u8; NODE_ID_SIZE]) -> Self {
        Self(Arc::new(node_id))
    }

    pub(crate) fn as_array(&self) -> &[u8; NODE_ID_SIZE] {
        &self.0
    }

    pub(crate) fn bits(&self) -> &NodeIdBitSlice {
        self.0.view_bits()
    }
}

impl AsRef<[u8]> for NodeId {
    fn as_ref(&self) -> &[u8] {
        self.0.as_ref()
    }
}

impl From<(NodeId, SocketAddr)> for NodeContactInfo {
    fn from((id, endpoint): (NodeId, SocketAddr)) -> Self {
        Self { id, endpoint }
    }
}

impl Distance {
    pub(crate) fn measure(src: &NodeIdBitSlice, dst: &NodeIdBitSlice) -> Self {
        let mut distance = bitarr![u8, Msb0; 0; NODE_ID_BIT_SIZE];
        distance.copy_from_bitslice(src);
        distance ^= dst;
        Self(distance)
    }
}

fn format_node_id_bit_arr(node_id: &NodeIdBitArr) -> Hex {
    Hex(node_id.as_raw_slice())
}

fn parse_arc_node_id<'de, D>(deserializer: D) -> Result<Arc<[u8; NODE_ID_SIZE]>, D::Error>
where
    D: Deserializer<'de>,
{
    use g1_base::str::Hex;

    Ok(Arc::new(
        Hex::try_from(String::deserialize(deserializer)?.as_str())
            .map_err(|hex| de::Error::custom(format!("invalid node id: {:?}", hex)))?
            .into_inner(),
    ))
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl NodeId {
        pub(crate) fn min() -> Self {
            Self::new([0x00; NODE_ID_SIZE])
        }

        pub(crate) fn max() -> Self {
            Self::new([0xff; NODE_ID_SIZE])
        }
    }

    impl NodeContactInfo {
        pub(crate) fn new_mock(port: u16) -> Self {
            let mut id = [0u8; NODE_ID_SIZE];
            id[0..2].copy_from_slice(&port.to_be_bytes());
            Self {
                id: NodeId::new(id),
                endpoint: SocketAddr::new("127.0.0.1".parse().unwrap(), port),
            }
        }
    }
}
