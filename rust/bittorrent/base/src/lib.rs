#[cfg(feature = "cli")]
pub mod cli;
#[cfg(feature = "compact")]
pub mod compact;

#[cfg(feature = "param")]
mod peer_id;

use std::array::TryFromSliceError;
use std::borrow::Borrow;
use std::cmp::{self, Ordering};
use std::iter;
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
g1_param::define!(pub block_size: u64 = 16384);

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

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Dimension {
    pub num_pieces: usize,

    pub piece_size: u64,
    last_piece_size: u64,

    pub size: u64,

    pub block_size: u64,

    pub end: BlockOffset,
}

impl Dimension {
    pub fn new(num_pieces: usize, piece_size: u64, size: u64, block_size: u64) -> Self {
        // Should we allow an empty torrent?
        assert!(num_pieces > 0 && piece_size > 0 && size > 0);
        assert!(block_size > 0);
        let num_pieces_u64 = u64::try_from(num_pieces).unwrap();
        assert!((num_pieces_u64 - 1) * piece_size < size && size <= num_pieces_u64 * piece_size);
        let last_piece_size = size - (num_pieces_u64 - 1) * piece_size;
        let end = BlockOffset::from((
            usize::try_from(size / piece_size).unwrap(),
            size % piece_size,
        ));
        Self {
            num_pieces,
            piece_size,
            last_piece_size,
            size,
            block_size,
            end,
        }
    }

    pub fn check_piece_index(&self, index: PieceIndex) -> Option<PieceIndex> {
        (usize::from(index) < self.num_pieces).then_some(index)
    }

    pub fn check_block_offset(&self, offset: BlockOffset) -> Option<BlockOffset> {
        (offset <= self.end && offset.1 < self.piece_size).then_some(offset)
    }

    pub fn check_block_desc(&self, desc: BlockDesc) -> Option<BlockDesc> {
        let BlockDesc(offset, size) = desc;
        let BlockOffset(index, offset) = self.check_block_offset(offset)?;
        // For now, we do not allow a block to span across pieces.
        (size <= self.block_size && offset + size <= self.checked_piece_size(index).unwrap_or(0))
            .then_some(desc)
    }

    pub fn piece_size(&self, index: PieceIndex) -> u64 {
        match self.checked_piece_size(index) {
            Some(piece_size) => piece_size,
            None => std::panic!("expect index < {}: {:?}", self.num_pieces, index),
        }
    }

    pub fn checked_piece_size(&self, index: PieceIndex) -> Option<u64> {
        match (usize::from(index) + 1).cmp(&self.num_pieces) {
            Ordering::Less => Some(self.piece_size),
            Ordering::Equal => Some(self.last_piece_size),
            Ordering::Greater => None,
        }
    }

    pub fn block_descs(&self, index: PieceIndex) -> impl Iterator<Item = BlockDesc> {
        let block_size = self.block_size;
        let piece_size = self.piece_size(index);
        let index = usize::from(index);
        let mut offset = 0;
        iter::from_fn(move || {
            if offset < piece_size {
                let size = cmp::min(piece_size - offset, block_size);
                let desc = (index, offset, size).into();
                offset += size;
                Some(desc)
            } else {
                None
            }
        })
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

    #[test]
    fn dimension_end() {
        assert_eq!(Dimension::new(1, 1, 1, 1).end, (1, 0).into());
        assert_eq!(Dimension::new(2, 2, 3, 1).end, (1, 1).into());
        assert_eq!(Dimension::new(2, 2, 4, 1).end, (2, 0).into());
        assert_eq!(Dimension::new(3, 4, 11, 1).end, (2, 3).into());
        assert_eq!(Dimension::new(3, 4, 12, 1).end, (3, 0).into());
    }

    #[test]
    fn dimension_check_piece_index() {
        let dim = Dimension::new(1, 1, 1, 1);
        assert_eq!(dim.check_piece_index(0.into()), Some(0.into()));
        assert_eq!(dim.check_piece_index(1.into()), None);

        let dim = Dimension::new(2, 2, 3, 1);
        assert_eq!(dim.check_piece_index(0.into()), Some(0.into()));
        assert_eq!(dim.check_piece_index(1.into()), Some(1.into()));
        assert_eq!(dim.check_piece_index(2.into()), None);

        let dim = Dimension::new(3, 4, 11, 1);
        assert_eq!(dim.check_piece_index(0.into()), Some(0.into()));
        assert_eq!(dim.check_piece_index(2.into()), Some(2.into()));
        assert_eq!(dim.check_piece_index(3.into()), None);
    }

    #[test]
    fn dimension_check_block_offset() {
        let dim = Dimension::new(1, 1, 1, 1);
        assert_eq!(dim.check_block_offset((0, 0).into()), Some((0, 0).into()));
        assert_eq!(dim.check_block_offset((0, 1).into()), None);
        assert_eq!(dim.check_block_offset((1, 0).into()), Some((1, 0).into()));

        let dim = Dimension::new(2, 2, 3, 1);
        assert_eq!(dim.check_block_offset((0, 1).into()), Some((0, 1).into()));
        assert_eq!(dim.check_block_offset((0, 2).into()), None);
        assert_eq!(dim.check_block_offset((1, 1).into()), Some((1, 1).into()));
        assert_eq!(dim.check_block_offset((2, 0).into()), None);

        let dim = Dimension::new(2, 2, 4, 1);
        assert_eq!(dim.check_block_offset((2, 0).into()), Some((2, 0).into()));
        assert_eq!(dim.check_block_offset((2, 1).into()), None);

        let dim = Dimension::new(3, 4, 11, 1);
        assert_eq!(dim.check_block_offset((0, 4).into()), None);
        assert_eq!(dim.check_block_offset((2, 3).into()), Some((2, 3).into()));
        assert_eq!(dim.check_block_offset((2, 3).into()), Some((2, 3).into()));
        assert_eq!(dim.check_block_offset((3, 0).into()), None);

        let dim = Dimension::new(3, 4, 12, 1);
        assert_eq!(dim.check_block_offset((3, 0).into()), Some((3, 0).into()));
    }

    #[test]
    fn dimension_check_block_desc() {
        fn test_some(dim: &Dimension, expect: (usize, u64, u64)) {
            let expect = expect.into();
            assert_eq!(dim.check_block_desc(expect), Some(expect));
        }

        let dim = Dimension::new(1, 1, 1, 1);
        test_some(&dim, (0, 0, 0));
        test_some(&dim, (0, 0, 1));
        test_some(&dim, (1, 0, 0));
        assert_eq!(dim.check_block_desc((1, 0, 1).into()), None);

        let dim = Dimension::new(3, 4, 11, 2);
        test_some(&dim, (0, 0, 2));
        assert_eq!(dim.check_block_desc((0, 0, 3).into()), None);
        test_some(&dim, (0, 3, 1));
        assert_eq!(dim.check_block_desc((0, 3, 2).into()), None);
        test_some(&dim, (2, 1, 2));
        assert_eq!(dim.check_block_desc((2, 2, 2).into()), None);

        let dim = Dimension::new(3, 4, 11, 6);
        test_some(&dim, (0, 0, 4));
        assert_eq!(dim.check_block_desc((0, 0, 5).into()), None);
        test_some(&dim, (2, 0, 3));
        assert_eq!(dim.check_block_desc((2, 0, 4).into()), None);
    }

    #[test]
    fn dimension_piece_size() {
        fn test(dim: Dimension, expect: &[u64]) {
            for (index, piece_size) in expect.iter().copied().enumerate() {
                assert_eq!(dim.piece_size(index.into()), piece_size);
                assert_eq!(dim.checked_piece_size(index.into()), Some(piece_size));
            }
            assert_eq!(dim.checked_piece_size(expect.len().into()), None);
        }

        test(Dimension::new(1, 1, 1, 1), &[1]);
        test(Dimension::new(2, 2, 3, 1), &[2, 1]);
        test(Dimension::new(2, 2, 4, 1), &[2, 2]);
        test(Dimension::new(3, 4, 11, 1), &[4, 4, 3]);
        test(Dimension::new(3, 4, 12, 1), &[4, 4, 4]);
    }

    #[test]
    fn dimension_block_descs() {
        fn test(dim: &Dimension, index: usize, expect: &[(usize, u64, u64)]) {
            let expect: Vec<_> = expect.iter().copied().map(BlockDesc::from).collect();
            assert_eq!(dim.block_descs(index.into()).collect::<Vec<_>>(), expect);
        }

        let dim = Dimension::new(1, 1, 1, 1);
        test(&dim, 0, &[(0, 0, 1)]);

        let dim = Dimension::new(2, 2, 3, 1);
        test(&dim, 0, &[(0, 0, 1), (0, 1, 1)]);
        test(&dim, 1, &[(1, 0, 1)]);

        let dim = Dimension::new(3, 4, 11, 3);
        test(&dim, 0, &[(0, 0, 3), (0, 3, 1)]);
        test(&dim, 1, &[(1, 0, 3), (1, 3, 1)]);
        test(&dim, 2, &[(2, 0, 3)]);

        let dim = Dimension::new(3, 4, 11, 5);
        test(&dim, 0, &[(0, 0, 4)]);
        test(&dim, 1, &[(1, 0, 4)]);
        test(&dim, 2, &[(2, 0, 3)]);
    }
}
