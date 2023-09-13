use std::io;
use std::ops::RangeInclusive;
use std::path::PathBuf;

use snafu::prelude::*;

use bittorrent_base::{BlockDesc, BlockOffset};

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    ExpectNonEmptyFile,
    ExpectNonEmptyFileList,
    ExpectNonZeroNumPieces,
    ExpectNonZeroPieceSize,
    #[snafu(display("expect total size in {range:?}: {size}"))]
    InvalidTotalFileSize {
        size: u64,
        range: RangeInclusive<u64>,
    },

    #[snafu(display("expect block offset <= {end:?}: {offset:?}"))]
    InvalidBlockOffset {
        offset: BlockOffset,
        end: BlockOffset,
    },
    #[snafu(display("expect block to fit inside one piece: {desc:?}"))]
    InvalidBlockDesc {
        desc: BlockDesc,
    },

    #[snafu(display("expect directory: {path:?}"))]
    ExpectDirectory {
        path: PathBuf,
    },
    #[snafu(display("expect relative path: \"{path}\""))]
    ExpectRelpath {
        path: String,
    },
}

impl From<Error> for io::Error {
    fn from(error: Error) -> Self {
        Self::other(error)
    }
}
