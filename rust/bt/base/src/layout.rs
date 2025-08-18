use std::cmp::Ordering;
use std::iter::Step;

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
}

impl Layout {
    pub fn new(size: u64, num_pieces: u32, piece_size: u64) -> Result<Self, Error> {
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

        Ok(Self {
            size,
            num_pieces,
            piece_size,
            last_piece_size,
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

    /// Returns the offset relative to the start of the torrent, not to the start of a piece.
    ///
    /// It accepts `index` not only less than but also equal to the number of pieces.
    pub fn piece_offset(&self, PieceIndex(index): PieceIndex) -> u64 {
        if index < self.num_pieces {
            u64::from(index) * self.piece_size
        } else if index == self.num_pieces {
            self.size
        } else {
            panic!("piece index out of range: {index}")
        }
    }

    /// Given an offset relative to the start of the torrent, translates it into a piece index and
    /// an offset within that piece.
    ///
    /// It accepts `offset` not only less than but also equal to the torrent size.
    pub fn to_piece_index(&self, offset: u64) -> (PieceIndex, u64) {
        assert!(offset <= self.size, "torrent offset out of range: {offset}");
        (
            PieceIndex((offset / self.piece_size).try_into().expect("piece index")),
            offset % self.piece_size,
        )
    }

    pub fn piece_size(&self, PieceIndex(index): PieceIndex) -> u64 {
        match (index + 1).cmp(&self.num_pieces) {
            Ordering::Less => self.piece_size,
            Ordering::Equal => self.last_piece_size,
            Ordering::Greater => std::panic!("piece index out of range: {index}"),
        }
    }

    /// Divides a piece into blocks.
    pub fn blocks(
        &self,
        index: PieceIndex,
        block_size: u64,
    ) -> impl Iterator<Item = BlockRange> + 'static {
        assert!(block_size != 0);
        let piece_size = self.piece_size(index);
        (0..)
            .map(move |i| i * block_size)
            .take_while(move |offset| offset < &piece_size)
            .map(move |offset| BlockRange(index, offset, block_size.min(piece_size - offset)))
    }
}

impl Step for PieceIndex {
    fn steps_between(start: &Self, end: &Self) -> (usize, Option<usize>) {
        Step::steps_between(&start.0, &end.0)
    }

    fn forward_checked(start: Self, count: usize) -> Option<Self> {
        Step::forward_checked(start.0, count).map(Self)
    }

    fn backward_checked(start: Self, count: usize) -> Option<Self> {
        Step::backward_checked(start.0, count).map(Self)
    }

    fn forward(start: Self, count: usize) -> Self {
        Self(Step::forward(start.0, count))
    }

    unsafe fn forward_unchecked(start: Self, count: usize) -> Self {
        Self(unsafe { Step::forward_unchecked(start.0, count) })
    }

    fn backward(start: Self, count: usize) -> Self {
        Self(Step::backward(start.0, count))
    }

    unsafe fn backward_unchecked(start: Self, count: usize) -> Self {
        Self(unsafe { Step::backward_unchecked(start.0, count) })
    }
}

#[cfg(test)]
mod tests {
    use std::ops::Range;

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
            Layout::new(1, 1, 1),
            Ok(Layout {
                size: 1,
                num_pieces: 1,
                piece_size: 1,
                last_piece_size: 1,
            }),
        );
        assert_eq!(
            Layout::new(5, 2, 3),
            Ok(Layout {
                size: 5,
                num_pieces: 2,
                piece_size: 3,
                last_piece_size: 2,
            }),
        );

        assert_eq!(
            Layout::new(0, 1, 2),
            Err(Error::Empty {
                size: 0,
                num_pieces: 1,
                piece_size: 2,
            }),
        );
        assert_eq!(
            Layout::new(1, 0, 2),
            Err(Error::Empty {
                size: 1,
                num_pieces: 0,
                piece_size: 2,
            }),
        );
        assert_eq!(
            Layout::new(1, 2, 0),
            Err(Error::Empty {
                size: 1,
                num_pieces: 2,
                piece_size: 0,
            }),
        );

        assert_eq!(
            Layout::new(3, 2, 3),
            Err(Error::Size {
                size: 3,
                lower: 3,
                upper: 6,
            }),
        );
        assert_eq!(
            Layout::new(7, 2, 3),
            Err(Error::Size {
                size: 7,
                lower: 3,
                upper: 6,
            }),
        );
    }

    #[test]
    fn check_range() {
        let layout = Layout::new(5, 2, 3).unwrap();

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
    fn piece_offset() {
        let layout = Layout::new(3, 3, 1).unwrap();
        assert_eq!(layout.piece_offset(PieceIndex(0)), 0);
        assert_eq!(layout.piece_offset(PieceIndex(1)), 1);
        assert_eq!(layout.piece_offset(PieceIndex(2)), 2);
        assert_eq!(layout.piece_offset(PieceIndex(3)), 3);

        let layout = Layout::new(12, 3, 5).unwrap();
        assert_eq!(layout.piece_offset(PieceIndex(0)), 0);
        assert_eq!(layout.piece_offset(PieceIndex(1)), 5);
        assert_eq!(layout.piece_offset(PieceIndex(2)), 10);
        assert_eq!(layout.piece_offset(PieceIndex(3)), 12);

        let layout = Layout::new(10, 2, 5).unwrap();
        assert_eq!(layout.piece_offset(PieceIndex(0)), 0);
        assert_eq!(layout.piece_offset(PieceIndex(1)), 5);
        assert_eq!(layout.piece_offset(PieceIndex(2)), 10);
    }

    #[test]
    fn to_piece_index() {
        let layout = Layout::new(3, 3, 1).unwrap();
        assert_eq!(layout.to_piece_index(0), (PieceIndex(0), 0));
        assert_eq!(layout.to_piece_index(1), (PieceIndex(1), 0));
        assert_eq!(layout.to_piece_index(2), (PieceIndex(2), 0));
        assert_eq!(layout.to_piece_index(3), (PieceIndex(3), 0));

        let layout = Layout::new(12, 3, 5).unwrap();
        assert_eq!(layout.to_piece_index(0), (PieceIndex(0), 0));
        assert_eq!(layout.to_piece_index(1), (PieceIndex(0), 1));
        assert_eq!(layout.to_piece_index(4), (PieceIndex(0), 4));
        assert_eq!(layout.to_piece_index(5), (PieceIndex(1), 0));
        assert_eq!(layout.to_piece_index(6), (PieceIndex(1), 1));
        assert_eq!(layout.to_piece_index(9), (PieceIndex(1), 4));
        assert_eq!(layout.to_piece_index(10), (PieceIndex(2), 0));
        assert_eq!(layout.to_piece_index(11), (PieceIndex(2), 1));
        assert_eq!(layout.to_piece_index(12), (PieceIndex(2), 2));

        let layout = Layout::new(10, 2, 5).unwrap();
        assert_eq!(layout.to_piece_index(0), (PieceIndex(0), 0));
        assert_eq!(layout.to_piece_index(9), (PieceIndex(1), 4));
        assert_eq!(layout.to_piece_index(10), (PieceIndex(2), 0));
    }

    #[test]
    fn piece_size() {
        for (size, expect) in [(4, 1), (5, 2), (6, 3)] {
            let layout = Layout::new(size, 2, 3).unwrap();
            assert_eq!(layout.piece_size(i(0)), 3);
            assert_eq!(layout.piece_size(i(1)), expect);
        }

        for (size, expect) in [(10, 2), (11, 3), (12, 4)] {
            let layout = Layout::new(size, 3, 4).unwrap();
            assert_eq!(layout.piece_size(i(0)), 4);
            assert_eq!(layout.piece_size(i(1)), 4);
            assert_eq!(layout.piece_size(i(2)), expect);
        }
    }

    #[test]
    fn blocks() {
        let layout = Layout::new(13, 2, 8).unwrap();
        assert_eq!(
            layout.blocks(i(1), 1).collect::<Vec<_>>(),
            &[r(1, 0, 1), r(1, 1, 1), r(1, 2, 1), r(1, 3, 1), r(1, 4, 1)],
        );
        assert_eq!(
            layout.blocks(i(1), 2).collect::<Vec<_>>(),
            &[r(1, 0, 2), r(1, 2, 2), r(1, 4, 1)],
        );
        assert_eq!(
            layout.blocks(i(1), 3).collect::<Vec<_>>(),
            &[r(1, 0, 3), r(1, 3, 2)],
        );
        assert_eq!(layout.blocks(i(1), 5).collect::<Vec<_>>(), &[r(1, 0, 5)]);
    }

    #[test]
    fn piece_index_range() {
        fn test(range: Range<PieceIndex>, expect: Range<u32>) {
            assert_eq!(
                range.clone().collect::<Vec<_>>(),
                expect.clone().map(PieceIndex).collect::<Vec<_>>(),
            );
            assert_eq!(range.count(), expect.count());
        }

        test(PieceIndex(0)..PieceIndex(0), 0..0);
        test(PieceIndex(0)..PieceIndex(1), 0..1);
        test(PieceIndex(0)..PieceIndex(3), 0..3);
        test(PieceIndex(3)..PieceIndex(7), 3..7);
        test(PieceIndex(1)..PieceIndex(0), 1..0);
    }
}
