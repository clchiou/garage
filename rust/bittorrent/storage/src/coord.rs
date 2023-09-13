use std::cmp::{self, Ordering};

use snafu::prelude::*;

use bittorrent_base::{BlockDesc, BlockOffset, PieceIndex};

use crate::{error, FileBlockDesc, FileBlockOffset};

/// Converts `BlockOffset` to `FileBlockOffset`.
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct CoordSys {
    num_pieces: usize,
    piece_size: u64,
    /// Maps file indexes to block offsets.
    file_ends: Vec<BlockOffset>,
}

impl CoordSys {
    pub(crate) fn new(
        num_pieces: usize,
        piece_size: u64,
        file_sizes: impl Iterator<Item = u64>,
    ) -> Result<Self, error::Error> {
        ensure!(num_pieces > 0, error::ExpectNonZeroNumPiecesSnafu);
        ensure!(piece_size > 0, error::ExpectNonZeroPieceSizeSnafu);

        let mut end = BlockOffset::from((0, 0));
        let file_ends: Vec<_> = file_sizes
            .map(move |file_size| {
                // Forbid zero `file_size`, as otherwise, binary search may return any one of the
                // matches when there are multiple matches.
                ensure!(file_size > 0, error::ExpectNonEmptyFileSnafu);
                end = end.add_scalar(file_size, piece_size);
                Ok(end)
            })
            .try_collect()?;
        ensure!(!file_ends.is_empty(), error::ExpectNonEmptyFileListSnafu);

        let this = Self {
            num_pieces,
            piece_size,
            file_ends,
        };
        let size = this.size();
        let range = (this.piece_index_to_scalar((num_pieces - 1).into()) + 1)
            ..=this.piece_index_to_scalar(num_pieces.into());
        ensure!(
            range.contains(&size),
            error::InvalidTotalFileSizeSnafu { size, range },
        );
        Ok(this)
    }

    fn end(&self) -> BlockOffset {
        *self.file_ends.last().unwrap()
    }

    fn size(&self) -> u64 {
        self.end().to_scalar(self.piece_size)
    }

    fn piece_index_to_scalar(&self, index: PieceIndex) -> u64 {
        index.to_scalar(self.piece_size)
    }

    pub(crate) fn piece_size(&self, index: PieceIndex) -> u64 {
        match (usize::from(index) + 1).cmp(&self.num_pieces) {
            Ordering::Less => self.piece_size,
            Ordering::Equal => self.size() - index.to_scalar(self.piece_size),
            Ordering::Greater => std::panic!("expect index < {}: {:?}", self.num_pieces, index),
        }
    }

    fn check_block_offset(&self, offset: BlockOffset) -> Result<BlockOffset, error::Error> {
        let end = self.end();
        ensure!(
            offset <= end && offset.1 < self.piece_size,
            error::InvalidBlockOffsetSnafu { offset, end },
        );
        Ok(offset)
    }

    pub(crate) fn check_block_desc(&self, desc: BlockDesc) -> Result<BlockDesc, error::Error> {
        let BlockDesc(offset, size) = desc;
        let end = offset.add_scalar(size, self.piece_size);
        self.check_block_offset(offset)?;
        self.check_block_offset(end)?;
        ensure!(
            offset.0 == end.0 || (usize::from(offset.0) + 1 == usize::from(end.0) && end.1 == 0),
            error::InvalidBlockDescSnafu { desc },
        );
        Ok(desc)
    }

    pub(crate) fn to_file_descs(
        &self,
        desc: BlockDesc,
    ) -> Result<Vec<FileBlockDesc>, error::Error> {
        let mut file_descs = Vec::new();
        let BlockDesc(mut offset, mut size) = self.check_block_desc(desc)?;
        while size > 0 {
            let file_offset = self.to_file_offset(offset).unwrap().unwrap();
            let file_size = cmp::min(
                self.file_ends[usize::from(file_offset.0)].to_scalar(self.piece_size)
                    - offset.to_scalar(self.piece_size),
                size,
            );
            file_descs.push((file_offset, file_size).into());
            offset = offset.add_scalar(file_size, self.piece_size);
            size -= file_size;
        }
        Ok(file_descs)
    }

    pub(crate) fn to_file_offset(
        &self,
        offset: BlockOffset,
    ) -> Result<Option<FileBlockOffset>, error::Error> {
        self.check_block_offset(offset)?;

        let file_index = match self.file_ends.binary_search(&offset) {
            Ok(i) => i + 1,
            Err(i) => i,
        };
        if file_index == self.file_ends.len() {
            return Ok(None);
        }

        let start = if file_index == 0 {
            (0, 0).into()
        } else {
            self.file_ends[file_index - 1]
        };
        let file_offset = offset.to_scalar(self.piece_size) - start.to_scalar(self.piece_size);

        Ok(Some((file_index, file_offset).into()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new() {
        assert_eq!(
            CoordSys::new(1, 7, [7].into_iter()),
            Ok(CoordSys {
                num_pieces: 1,
                piece_size: 7,
                file_ends: vec![(1, 0).into()],
            }),
        );
        assert_eq!(
            CoordSys::new(2, 7, [1, 2, 7, 2].into_iter()),
            Ok(CoordSys {
                num_pieces: 2,
                piece_size: 7,
                file_ends: vec![(0, 1).into(), (0, 3).into(), (1, 3).into(), (1, 5).into()],
            }),
        );

        assert_eq!(
            CoordSys::new(0, 7, [1].into_iter()),
            Err(error::Error::ExpectNonZeroNumPieces),
        );
        assert_eq!(
            CoordSys::new(1, 0, [1].into_iter()),
            Err(error::Error::ExpectNonZeroPieceSize),
        );
        assert_eq!(
            CoordSys::new(1, 7, [0].into_iter()),
            Err(error::Error::ExpectNonEmptyFile),
        );
        assert_eq!(
            CoordSys::new(1, 7, [].into_iter()),
            Err(error::Error::ExpectNonEmptyFileList),
        );

        assert_eq!(
            CoordSys::new(2, 7, [7].into_iter()),
            Err(error::Error::InvalidTotalFileSize {
                size: 7,
                range: 8..=14,
            }),
        );
        assert_eq!(
            CoordSys::new(2, 7, [7, 8].into_iter()),
            Err(error::Error::InvalidTotalFileSize {
                size: 15,
                range: 8..=14,
            }),
        );
    }

    #[test]
    fn piece_size() {
        let coord_sys = CoordSys::new(2, 7, [1, 2, 7, 2].into_iter()).unwrap();
        assert_eq!(coord_sys.piece_size(0.into()), 7);
        assert_eq!(coord_sys.piece_size(1.into()), 5);

        let coord_sys = CoordSys::new(2, 7, [7, 4, 3].into_iter()).unwrap();
        assert_eq!(coord_sys.piece_size(0.into()), 7);
        assert_eq!(coord_sys.piece_size(1.into()), 7);
    }

    #[test]
    #[should_panic(expected = "expect index < 2: PieceIndex(2)")]
    fn piece_size_panic() {
        let coord_sys = CoordSys::new(2, 7, [10].into_iter()).unwrap();
        let _ = coord_sys.piece_size(2.into());
    }

    #[test]
    fn check_block_offset() {
        fn test_ok(coord_sys: &CoordSys, offset: (usize, u64)) {
            let offset = BlockOffset::from(offset);
            assert_eq!(coord_sys.check_block_offset(offset), Ok(offset));
        }

        let coord_sys = CoordSys::new(2, 7, [1, 2, 7, 2].into_iter()).unwrap();
        test_ok(&coord_sys, (0, 0));
        test_ok(&coord_sys, (0, 6));
        assert_eq!(
            coord_sys.check_block_offset((0, 7).into()),
            Err(error::Error::InvalidBlockOffset {
                offset: (0, 7).into(),
                end: (1, 5).into(),
            }),
        );

        test_ok(&coord_sys, (1, 0));
        test_ok(&coord_sys, (1, 5));
        assert_eq!(
            coord_sys.check_block_offset((1, 6).into()),
            Err(error::Error::InvalidBlockOffset {
                offset: (1, 6).into(),
                end: (1, 5).into(),
            }),
        );
    }

    #[test]
    fn check_block_desc() {
        fn test_ok(coord_sys: &CoordSys, desc: (usize, u64, u64)) {
            let desc = BlockDesc::from(desc);
            assert_eq!(coord_sys.check_block_desc(desc), Ok(desc));
        }

        let coord_sys = CoordSys::new(2, 7, [1, 2, 7, 2].into_iter()).unwrap();
        test_ok(&coord_sys, (0, 0, 0));
        test_ok(&coord_sys, (0, 0, 7));
        assert_eq!(
            coord_sys.check_block_desc((0, 0, 8).into()),
            Err(error::Error::InvalidBlockDesc {
                desc: (0, 0, 8).into(),
            }),
        );

        test_ok(&coord_sys, (1, 0, 0));
        test_ok(&coord_sys, (1, 0, 5));
        assert_eq!(
            coord_sys.check_block_desc((1, 0, 6).into()),
            Err(error::Error::InvalidBlockOffset {
                offset: (1, 6).into(),
                end: (1, 5).into(),
            }),
        );
    }

    #[test]
    fn to_file_descs() {
        fn test_ok(coord_sys: &CoordSys, desc: (usize, u64, u64), expect: &[(usize, u64, u64)]) {
            let expect: Vec<_> = expect.iter().copied().map(FileBlockDesc::from).collect();
            assert_eq!(coord_sys.to_file_descs(desc.into()), Ok(expect));
        }

        let coord_sys = CoordSys::new(1, 7, [4].into_iter()).unwrap();
        for offset in 0..4 {
            test_ok(&coord_sys, (0, offset, 0), &[]);
        }
        for size in 1..=4 {
            test_ok(&coord_sys, (0, 0, size), &[(0, 0, size)]);
        }
        assert_eq!(
            coord_sys.to_file_descs((0, 5, 0).into()),
            Err(error::Error::InvalidBlockOffset {
                offset: (0, 5).into(),
                end: (0, 4).into(),
            }),
        );

        test_ok(&coord_sys, (0, 1, 1), &[(0, 1, 1)]);
        test_ok(&coord_sys, (0, 3, 1), &[(0, 3, 1)]);
        assert_eq!(
            coord_sys.to_file_descs((0, 4, 1).into()),
            Err(error::Error::InvalidBlockOffset {
                offset: (0, 5).into(),
                end: (0, 4).into(),
            }),
        );

        let coord_sys = CoordSys::new(2, 7, [1, 2, 7, 2].into_iter()).unwrap();
        test_ok(&coord_sys, (0, 0, 7), &[(0, 0, 1), (1, 0, 2), (2, 0, 4)]);
        test_ok(&coord_sys, (0, 1, 6), &[(1, 0, 2), (2, 0, 4)]);
        test_ok(&coord_sys, (1, 0, 5), &[(2, 4, 3), (3, 0, 2)]);
    }

    #[test]
    fn to_file_offset() {
        fn test_ok(coord_sys: &CoordSys, offset: (usize, u64), expect: (usize, u64)) {
            assert_eq!(
                coord_sys.to_file_offset(offset.into()),
                Ok(Some(expect.into())),
            );
        }

        let coord_sys = CoordSys::new(1, 7, [4].into_iter()).unwrap();
        test_ok(&coord_sys, (0, 0), (0, 0));
        test_ok(&coord_sys, (0, 1), (0, 1));
        test_ok(&coord_sys, (0, 3), (0, 3));

        assert_eq!(coord_sys.to_file_offset((0, 4).into()), Ok(None));
        assert_eq!(
            coord_sys.to_file_offset((0, 5).into()),
            Err(error::Error::InvalidBlockOffset {
                offset: (0, 5).into(),
                end: (0, 4).into(),
            }),
        );

        let coord_sys = CoordSys::new(2, 7, [1, 2, 7, 2].into_iter()).unwrap();
        test_ok(&coord_sys, (0, 0), (0, 0));

        test_ok(&coord_sys, (0, 1), (1, 0));
        test_ok(&coord_sys, (0, 2), (1, 1));

        test_ok(&coord_sys, (0, 3), (2, 0));
        test_ok(&coord_sys, (0, 4), (2, 1));
        test_ok(&coord_sys, (1, 2), (2, 6));

        test_ok(&coord_sys, (1, 3), (3, 0));
        test_ok(&coord_sys, (1, 4), (3, 1));

        assert_eq!(coord_sys.to_file_offset((1, 5).into()), Ok(None));
        assert_eq!(
            coord_sys.to_file_offset((1, 6).into()),
            Err(error::Error::InvalidBlockOffset {
                offset: (1, 6).into(),
                end: (1, 5).into(),
            }),
        );
    }
}
