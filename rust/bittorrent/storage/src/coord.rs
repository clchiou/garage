use std::cmp;

use snafu::prelude::*;

use bittorrent_base::{BlockDesc, BlockOffset, Dimension};

use crate::{error, FileBlockDesc, FileBlockOffset};

/// Converts `BlockOffset` to `FileBlockOffset`.
#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct CoordSys {
    pub(crate) dim: Dimension,
    /// Maps file indexes to block offsets.
    file_ends: Vec<BlockOffset>,
}

impl CoordSys {
    pub(crate) fn new(
        dim: Dimension,
        file_sizes: impl Iterator<Item = u64>,
    ) -> Result<Self, error::Error> {
        let mut size = 0;
        let mut end = BlockOffset::from((0, 0));
        let file_ends: Vec<_> = file_sizes
            .map(|file_size| {
                // Forbid zero `file_size`, as otherwise, binary search may return any one of the
                // matches when there are multiple matches.
                ensure!(file_size > 0, error::ExpectNonEmptyFileSnafu);
                size += file_size;
                end = end.add_scalar(file_size, dim.piece_size);
                Ok(end)
            })
            .try_collect()?;
        ensure!(!file_ends.is_empty(), error::ExpectNonEmptyFileListSnafu);
        assert_eq!(dim.size, size);
        assert_eq!(&dim.end, file_ends.last().unwrap());
        Ok(Self { dim, file_ends })
    }

    fn check_block_offset(&self, offset: BlockOffset) -> Result<BlockOffset, error::Error> {
        self.dim
            .check_block_offset(offset)
            .ok_or(error::Error::InvalidBlockOffset { offset })
    }

    pub(crate) fn check_block_desc(&self, desc: BlockDesc) -> Result<BlockDesc, error::Error> {
        self.dim
            .check_block_desc(desc)
            .ok_or(error::Error::InvalidBlockDesc { desc })
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
                self.file_ends[usize::from(file_offset.0)].to_scalar(self.dim.piece_size)
                    - offset.to_scalar(self.dim.piece_size),
                size,
            );
            file_descs.push((file_offset, file_size).into());
            offset = offset.add_scalar(file_size, self.dim.piece_size);
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
        let file_offset =
            offset.to_scalar(self.dim.piece_size) - start.to_scalar(self.dim.piece_size);

        Ok(Some((file_index, file_offset).into()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const BLOCK_SIZE: u64 = 16384;

    fn new_coord_sys(
        num_pieces: usize,
        piece_size: u64,
        file_sizes: &[u64],
    ) -> Result<CoordSys, error::Error> {
        CoordSys::new(
            Dimension::new(num_pieces, piece_size, file_sizes.iter().sum(), BLOCK_SIZE),
            file_sizes.iter().copied(),
        )
    }

    #[test]
    fn new() {
        assert_eq!(
            new_coord_sys(1, 7, &[7]),
            Ok(CoordSys {
                dim: Dimension::new(1, 7, 7, BLOCK_SIZE),
                file_ends: vec![(1, 0).into()],
            }),
        );
        assert_eq!(
            new_coord_sys(2, 7, &[1, 2, 7, 2]),
            Ok(CoordSys {
                dim: Dimension::new(2, 7, 12, BLOCK_SIZE),
                file_ends: vec![(0, 1).into(), (0, 3).into(), (1, 3).into(), (1, 5).into()],
            }),
        );
        assert_eq!(
            CoordSys::new(Dimension::new(1, 7, 3, BLOCK_SIZE), [0].into_iter()),
            Err(error::Error::ExpectNonEmptyFile),
        );
        assert_eq!(
            CoordSys::new(Dimension::new(1, 7, 3, BLOCK_SIZE), [].into_iter()),
            Err(error::Error::ExpectNonEmptyFileList),
        );
    }

    #[test]
    fn piece_size() {
        let coord_sys = new_coord_sys(2, 7, &[1, 2, 7, 2]).unwrap();
        assert_eq!(coord_sys.dim.piece_size(0.into()), 7);
        assert_eq!(coord_sys.dim.piece_size(1.into()), 5);

        let coord_sys = new_coord_sys(2, 7, &[7, 4, 3]).unwrap();
        assert_eq!(coord_sys.dim.piece_size(0.into()), 7);
        assert_eq!(coord_sys.dim.piece_size(1.into()), 7);
    }

    #[test]
    #[should_panic(expected = "expect index < 2: PieceIndex(2)")]
    fn piece_size_panic() {
        let coord_sys = new_coord_sys(2, 7, &[10]).unwrap();
        let _ = coord_sys.dim.piece_size(2.into());
    }

    #[test]
    fn check_block_offset() {
        fn test_ok(coord_sys: &CoordSys, offset: (usize, u64)) {
            let offset = BlockOffset::from(offset);
            assert_eq!(coord_sys.check_block_offset(offset), Ok(offset));
        }

        fn test_err(coord_sys: &CoordSys, offset: (usize, u64)) {
            let offset = BlockOffset::from(offset);
            assert_eq!(
                coord_sys.check_block_offset(offset),
                Err(error::Error::InvalidBlockOffset { offset }),
            );
        }

        let coord_sys = new_coord_sys(2, 7, &[1, 2, 7, 2]).unwrap();
        test_ok(&coord_sys, (0, 0));
        test_ok(&coord_sys, (0, 6));
        test_err(&coord_sys, (0, 7));

        test_ok(&coord_sys, (1, 0));
        test_ok(&coord_sys, (1, 5));
        test_err(&coord_sys, (1, 6));
    }

    #[test]
    fn check_block_desc() {
        fn test_ok(coord_sys: &CoordSys, desc: (usize, u64, u64)) {
            let desc = BlockDesc::from(desc);
            assert_eq!(coord_sys.check_block_desc(desc), Ok(desc));
        }

        fn test_err(coord_sys: &CoordSys, desc: (usize, u64, u64)) {
            let desc = BlockDesc::from(desc);
            assert_eq!(
                coord_sys.check_block_desc(desc),
                Err(error::Error::InvalidBlockDesc { desc }),
            );
        }

        let coord_sys = new_coord_sys(2, 7, &[1, 2, 7, 2]).unwrap();
        test_ok(&coord_sys, (0, 0, 0));
        test_ok(&coord_sys, (0, 0, 7));
        test_err(&coord_sys, (0, 0, 8));

        test_ok(&coord_sys, (1, 0, 0));
        test_ok(&coord_sys, (1, 0, 5));
        test_err(&coord_sys, (1, 0, 6));
    }

    #[test]
    fn to_file_descs() {
        fn test_ok(coord_sys: &CoordSys, desc: (usize, u64, u64), expect: &[(usize, u64, u64)]) {
            let expect: Vec<_> = expect.iter().copied().map(FileBlockDesc::from).collect();
            assert_eq!(coord_sys.to_file_descs(desc.into()), Ok(expect));
        }

        fn test_err(coord_sys: &CoordSys, desc: (usize, u64, u64)) {
            let desc = BlockDesc::from(desc);
            assert_eq!(
                coord_sys.to_file_descs(desc),
                Err(error::Error::InvalidBlockDesc { desc }),
            );
        }

        let coord_sys = new_coord_sys(1, 7, &[4]).unwrap();
        for offset in 0..4 {
            test_ok(&coord_sys, (0, offset, 0), &[]);
        }
        for size in 1..=4 {
            test_ok(&coord_sys, (0, 0, size), &[(0, 0, size)]);
        }
        test_err(&coord_sys, (0, 5, 0));

        test_ok(&coord_sys, (0, 1, 1), &[(0, 1, 1)]);
        test_ok(&coord_sys, (0, 3, 1), &[(0, 3, 1)]);
        test_err(&coord_sys, (0, 4, 1));

        let coord_sys = new_coord_sys(2, 7, &[1, 2, 7, 2]).unwrap();
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

        fn test_err(coord_sys: &CoordSys, offset: (usize, u64)) {
            let offset = offset.into();
            assert_eq!(
                coord_sys.to_file_offset(offset),
                Err(error::Error::InvalidBlockOffset { offset }),
            );
        }

        let coord_sys = new_coord_sys(1, 7, &[4]).unwrap();
        test_ok(&coord_sys, (0, 0), (0, 0));
        test_ok(&coord_sys, (0, 1), (0, 1));
        test_ok(&coord_sys, (0, 3), (0, 3));

        assert_eq!(coord_sys.to_file_offset((0, 4).into()), Ok(None));
        test_err(&coord_sys, (0, 5));

        let coord_sys = new_coord_sys(2, 7, &[1, 2, 7, 2]).unwrap();
        test_ok(&coord_sys, (0, 0), (0, 0));

        test_ok(&coord_sys, (0, 1), (1, 0));
        test_ok(&coord_sys, (0, 2), (1, 1));

        test_ok(&coord_sys, (0, 3), (2, 0));
        test_ok(&coord_sys, (0, 4), (2, 1));
        test_ok(&coord_sys, (1, 2), (2, 6));

        test_ok(&coord_sys, (1, 3), (3, 0));
        test_ok(&coord_sys, (1, 4), (3, 1));

        assert_eq!(coord_sys.to_file_offset((1, 5).into()), Ok(None));
        test_err(&coord_sys, (1, 6));
    }
}
