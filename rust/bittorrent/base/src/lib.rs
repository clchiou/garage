#![cfg_attr(feature = "compact", feature(return_position_impl_trait_in_trait))]

#[cfg(feature = "compact")]
pub mod compact;

#[cfg(feature = "param")]
mod peer_id;

use std::array::TryFromSliceError;
use std::borrow::Borrow;
use std::sync::Arc;

#[cfg(feature = "param")]
use serde::Deserialize;

use g1_base::fmt::{DebugExt, EscapeAscii, Hex};

pub const PROTOCOL_ID: &[u8] = b"BitTorrent protocol";

pub const INFO_HASH_SIZE: usize = 20;
pub const PIECE_HASH_SIZE: usize = 20;

pub const PEER_ID_SIZE: usize = 20;

pub const NODE_ID_SIZE: usize = 20; // BEP 5.

// These parameters are not declared as `pub` because they should only be accessed via
// `Features::load`.
#[cfg(feature = "param")]
g1_param::define!(dht_enable: bool = true); // BEP 5
#[cfg(feature = "param")]
g1_param::define!(fast_enable: bool = true); // BEP 6
#[cfg(feature = "param")]
g1_param::define!(extension_enable: bool = true); // BEP 10

#[cfg(feature = "param")]
g1_param::define!(pub self_id: PeerId = PeerId::new(peer_id::generate()));

#[cfg(feature = "param")]
g1_param::define!(pub recv_buffer_capacity: usize = 65536);
#[cfg(feature = "param")]
g1_param::define!(pub send_buffer_capacity: usize = 65536);

#[cfg(feature = "param")]
g1_param::define!(pub payload_size_limit: usize = 65536);

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Features {
    pub dht: bool,
    pub fast: bool,
    pub extension: bool,
}

impl Features {
    #[cfg(feature = "param")]
    pub fn load() -> Self {
        Self::new(*dht_enable(), *fast_enable(), *extension_enable())
    }

    pub fn new(dht: bool, fast: bool, extension: bool) -> Self {
        Self {
            dht,
            fast,
            extension,
        }
    }
}

#[derive(Clone, DebugExt, Eq, Hash, PartialEq)]
pub struct InfoHash(#[debug(with = Hex)] Arc<[u8; INFO_HASH_SIZE]>);

impl<'a> TryFrom<&'a [u8]> for InfoHash {
    type Error = TryFromSliceError;

    fn try_from(info_hash: &'a [u8]) -> Result<InfoHash, TryFromSliceError> {
        info_hash.try_into().map(InfoHash::new)
    }
}

impl InfoHash {
    pub fn new(info_hash: [u8; INFO_HASH_SIZE]) -> Self {
        Self(Arc::new(info_hash))
    }
}

impl AsRef<[u8]> for InfoHash {
    fn as_ref(&self) -> &[u8] {
        self.0.as_ref()
    }
}

impl Borrow<[u8]> for InfoHash {
    fn borrow(&self) -> &[u8] {
        self.0.as_slice()
    }
}

#[derive(Clone, DebugExt, Eq, Hash, PartialEq)]
#[cfg_attr(feature = "param", derive(Deserialize))]
pub struct PeerId(
    #[debug(with = EscapeAscii)]
    #[cfg_attr(feature = "param", serde(deserialize_with = "peer_id::parse"))]
    Arc<[u8; PEER_ID_SIZE]>,
);

impl<'a> TryFrom<&'a [u8]> for PeerId {
    type Error = TryFromSliceError;

    fn try_from(peer_id: &'a [u8]) -> Result<PeerId, TryFromSliceError> {
        peer_id.try_into().map(PeerId::new)
    }
}

impl PeerId {
    pub fn new(peer_id: [u8; PEER_ID_SIZE]) -> Self {
        Self(Arc::new(peer_id))
    }

    pub fn as_array(&self) -> &[u8; PEER_ID_SIZE] {
        &self.0
    }
}

impl AsRef<[u8]> for PeerId {
    fn as_ref(&self) -> &[u8] {
        self.0.as_ref()
    }
}

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct PieceIndex(pub usize);

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct BlockOffset(pub PieceIndex, pub u64);

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct BlockDesc(pub BlockOffset, pub u64);

impl From<usize> for PieceIndex {
    fn from(index: usize) -> Self {
        Self(index)
    }
}

impl From<PieceIndex> for usize {
    fn from(PieceIndex(index): PieceIndex) -> Self {
        index
    }
}

impl PieceIndex {
    pub fn to_scalar(self, piece_size: u64) -> u64 {
        u64::try_from(usize::from(self)).unwrap() * piece_size
    }
}

impl From<(usize, u64)> for BlockOffset {
    fn from((index, offset): (usize, u64)) -> Self {
        Self(index.into(), offset)
    }
}

impl From<(PieceIndex, u64)> for BlockOffset {
    fn from((index, offset): (PieceIndex, u64)) -> Self {
        Self(index, offset)
    }
}

impl From<BlockOffset> for (usize, u64) {
    fn from(BlockOffset(PieceIndex(index), offset): BlockOffset) -> Self {
        (index, offset)
    }
}

impl BlockOffset {
    fn check(offset: u64, piece_size: u64) {
        assert!(
            offset < piece_size,
            "expect block offset < {}: {}",
            piece_size,
            offset,
        );
    }

    pub fn add_scalar(self, scalar: u64, piece_size: u64) -> Self {
        let (index, offset) = self.into();
        Self::check(offset, piece_size);
        let offset = offset + scalar;
        let index = index + usize::try_from(offset / piece_size).unwrap();
        (index, offset % piece_size).into()
    }

    pub fn to_scalar(self, piece_size: u64) -> u64 {
        let Self(index, offset) = self;
        Self::check(offset, piece_size);
        index.to_scalar(piece_size) + offset
    }
}

impl From<(usize, u64, u64)> for BlockDesc {
    fn from((index, offset, size): (usize, u64, u64)) -> Self {
        Self((index, offset).into(), size)
    }
}

impl From<(BlockOffset, u64)> for BlockDesc {
    fn from((offset, size): (BlockOffset, u64)) -> Self {
        Self(offset, size)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn piece_index_to_scalar() {
        assert_eq!(PieceIndex::from(0).to_scalar(1), 0);
        assert_eq!(PieceIndex::from(1).to_scalar(1), 1);
        assert_eq!(PieceIndex::from(2).to_scalar(1), 2);
        assert_eq!(PieceIndex::from(0).to_scalar(2), 0);
        assert_eq!(PieceIndex::from(1).to_scalar(2), 2);
        assert_eq!(PieceIndex::from(2).to_scalar(2), 4);
        assert_eq!(PieceIndex::from(0).to_scalar(3), 0);
        assert_eq!(PieceIndex::from(1).to_scalar(3), 3);
        assert_eq!(PieceIndex::from(2).to_scalar(3), 6);
    }

    #[test]
    fn block_offset_add_scalar() {
        let x = BlockOffset::from((0, 0));
        assert_eq!(x.add_scalar(0, 1), (0, 0).into());
        assert_eq!(x.add_scalar(1, 1), (1, 0).into());
        assert_eq!(x.add_scalar(2, 1), (2, 0).into());
        assert_eq!(x.add_scalar(3, 1), (3, 0).into());

        assert_eq!(x.add_scalar(0, 2), (0, 0).into());
        assert_eq!(x.add_scalar(1, 2), (0, 1).into());
        assert_eq!(x.add_scalar(2, 2), (1, 0).into());
        assert_eq!(x.add_scalar(3, 2), (1, 1).into());

        let x = BlockOffset::from((2, 1));
        assert_eq!(x.add_scalar(0, 3), (2, 1).into());
        assert_eq!(x.add_scalar(1, 3), (2, 2).into());
        assert_eq!(x.add_scalar(2, 3), (3, 0).into());
        assert_eq!(x.add_scalar(3, 3), (3, 1).into());
    }

    #[test]
    fn block_offset_to_scalar() {
        assert_eq!(BlockOffset::from((0, 0)).to_scalar(1), 0);
        assert_eq!(BlockOffset::from((1, 0)).to_scalar(1), 1);
        assert_eq!(BlockOffset::from((2, 0)).to_scalar(1), 2);
        assert_eq!(BlockOffset::from((3, 0)).to_scalar(1), 3);

        assert_eq!(BlockOffset::from((0, 0)).to_scalar(2), 0);
        assert_eq!(BlockOffset::from((0, 1)).to_scalar(2), 1);
        assert_eq!(BlockOffset::from((1, 0)).to_scalar(2), 2);
        assert_eq!(BlockOffset::from((1, 1)).to_scalar(2), 3);

        assert_eq!(BlockOffset::from((2, 1)).to_scalar(5), 11);
    }
}
