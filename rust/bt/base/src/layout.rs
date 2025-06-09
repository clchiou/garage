use std::cmp::Ordering;
use std::iter;

use snafu::prelude::*;

//
// A torrent is divided into pieces, and each piece is further divided into blocks.
//

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
pub enum Error {
    #[snafu(display(
        "expect non-empty torrent: size={size} num_pieces={num_pieces} piece_size={piece_size}"
    ))]
    Empty {
        size: u64,
        num_pieces: u32,
        piece_size: u64,
    },
    #[snafu(display("expect {lower} < size <= {upper}: {size}"))]
    Size { size: u64, lower: u64, upper: u64 },

    #[snafu(display("expect 0 < block_size <= {piece_size}: {block_size}"))]
    BlockSize { block_size: u64, piece_size: u64 },
}

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct PieceIndex(pub u32);

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct BlockRange(pub PieceIndex, pub u64, pub u64);

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Layout {
    size: u64,
    num_pieces: u32,
    piece_size: u64,
    last_piece_size: u64,
    block_size: u64,
}

impl Layout {
    pub fn new(
        size: u64,
        num_pieces: u32,
        piece_size: u64,
        block_size: u64,
    ) -> Result<Self, Error> {
        ensure!(
            size > 0 && num_pieces > 0 && piece_size > 0,
            EmptySnafu {
                size,
                num_pieces,
                piece_size,
            },
        );

        let n = u64::from(num_pieces);
        let lower = (n - 1) * piece_size;
        let upper = n * piece_size;
        ensure!(
            lower < size && size <= upper,
            SizeSnafu { size, lower, upper },
        );
        let last_piece_size = size - lower;

        ensure!(
            0 < block_size && block_size <= piece_size,
            BlockSizeSnafu {
                block_size,
                piece_size,
            },
        );

        Ok(Self {
            size,
            num_pieces,
            piece_size,
            last_piece_size,
            block_size,
        })
    }

    pub fn check_index(&self, PieceIndex(index): PieceIndex) -> bool {
        index < self.num_pieces
    }

    pub fn check_range(&self, BlockRange(index, offset, size): BlockRange) -> bool {
        self.check_index(index)
            && size > 0
            // For now, we do not allow a block to span across pieces.
            && offset + size <= self.piece_size(index)
    }

    pub fn size(&self) -> u64 {
        self.size
    }

    pub fn num_pieces(&self) -> u32 {
        self.num_pieces
    }

    pub fn piece_indices(&self) -> impl Iterator<Item = PieceIndex> {
        (0..self.num_pieces).map(PieceIndex)
    }

    /// Returns the offset relative to the start of the torrent, not to the start of a piece.
    pub fn piece_offset(&self, PieceIndex(index): PieceIndex) -> u64 {
        assert!(index < self.num_pieces, "piece index out of range: {index}");
        u64::from(index) * self.piece_size
    }

    pub fn piece_size(&self, PieceIndex(index): PieceIndex) -> u64 {
        match (index + 1).cmp(&self.num_pieces) {
            Ordering::Less => self.piece_size,
            Ordering::Equal => self.last_piece_size,
            Ordering::Greater => std::panic!("piece index out of range: {index}"),
        }
    }

    pub fn block_ranges(&self, index: PieceIndex) -> impl Iterator<Item = BlockRange> {
        let piece_size = self.piece_size(index);
        let block_size = self.block_size;
        iter::successors(
            Some(BlockRange(index, 0, block_size.min(piece_size))),
            move |&BlockRange(index, mut offset, size)| {
                offset += size;
                (offset < piece_size)
                    .then(|| BlockRange(index, offset, block_size.min(piece_size - offset)))
            },
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn i(index: u32) -> PieceIndex {
        PieceIndex(index)
    }

    fn r(index: u32, offset: u64, size: u64) -> BlockRange {
        BlockRange(PieceIndex(index), offset, size)
    }

    #[test]
    fn new() {
        assert_eq!(
            Layout::new(1, 1, 1, 1),
            Ok(Layout {
                size: 1,
                num_pieces: 1,
                piece_size: 1,
                last_piece_size: 1,
                block_size: 1,
            }),
        );
        assert_eq!(
            Layout::new(5, 2, 3, 1),
            Ok(Layout {
                size: 5,
                num_pieces: 2,
                piece_size: 3,
                last_piece_size: 2,
                block_size: 1,
            }),
        );

        assert_eq!(
            Layout::new(0, 1, 2, 3),
            Err(Error::Empty {
                size: 0,
                num_pieces: 1,
                piece_size: 2,
            }),
        );
        assert_eq!(
            Layout::new(1, 0, 2, 3),
            Err(Error::Empty {
                size: 1,
                num_pieces: 0,
                piece_size: 2,
            }),
        );
        assert_eq!(
            Layout::new(1, 2, 0, 3),
            Err(Error::Empty {
                size: 1,
                num_pieces: 2,
                piece_size: 0,
            }),
        );

        assert_eq!(
            Layout::new(3, 2, 3, 1),
            Err(Error::Size {
                size: 3,
                lower: 3,
                upper: 6,
            }),
        );
        assert_eq!(
            Layout::new(7, 2, 3, 1),
            Err(Error::Size {
                size: 7,
                lower: 3,
                upper: 6,
            }),
        );

        assert_eq!(
            Layout::new(6, 2, 3, 0),
            Err(Error::BlockSize {
                block_size: 0,
                piece_size: 3,
            }),
        );
        assert_eq!(
            Layout::new(6, 2, 3, 4),
            Err(Error::BlockSize {
                block_size: 4,
                piece_size: 3,
            }),
        );
    }

    #[test]
    fn check_range() {
        let layout = Layout::new(5, 2, 3, 1).unwrap();

        assert_eq!(layout.check_range(r(0, 0, 0)), false);

        assert_eq!(layout.check_range(r(0, 0, 1)), true);
        assert_eq!(layout.check_range(r(0, 1, 1)), true);
        assert_eq!(layout.check_range(r(0, 2, 1)), true);
        assert_eq!(layout.check_range(r(0, 3, 1)), false);

        assert_eq!(layout.check_range(r(1, 0, 1)), true);
        assert_eq!(layout.check_range(r(1, 1, 1)), true);
        assert_eq!(layout.check_range(r(1, 2, 1)), false);

        assert_eq!(layout.check_range(r(2, 0, 1)), false);
    }

    #[test]
    fn piece_size() {
        for (size, expect) in [(4, 1), (5, 2), (6, 3)] {
            let layout = Layout::new(size, 2, 3, 1).unwrap();
            assert_eq!(layout.piece_size(i(0)), 3);
            assert_eq!(layout.piece_size(i(1)), expect);
        }

        for (size, expect) in [(10, 2), (11, 3), (12, 4)] {
            let layout = Layout::new(size, 3, 4, 1).unwrap();
            assert_eq!(layout.piece_size(i(0)), 4);
            assert_eq!(layout.piece_size(i(1)), 4);
            assert_eq!(layout.piece_size(i(2)), expect);
        }
    }

    #[test]
    fn block_ranges() {
        let layout = Layout::new(13, 2, 8, 1).unwrap();
        assert_eq!(
            layout.block_ranges(i(1)).collect::<Vec<_>>(),
            &[r(1, 0, 1), r(1, 1, 1), r(1, 2, 1), r(1, 3, 1), r(1, 4, 1)],
        );
        let layout = Layout::new(13, 2, 8, 2).unwrap();
        assert_eq!(
            layout.block_ranges(i(1)).collect::<Vec<_>>(),
            &[r(1, 0, 2), r(1, 2, 2), r(1, 4, 1)],
        );
        let layout = Layout::new(13, 2, 8, 3).unwrap();
        assert_eq!(
            layout.block_ranges(i(1)).collect::<Vec<_>>(),
            &[r(1, 0, 3), r(1, 3, 2)],
        );
        let layout = Layout::new(13, 2, 8, 5).unwrap();
        assert_eq!(layout.block_ranges(i(1)).collect::<Vec<_>>(), &[r(1, 0, 5)]);
    }
}
