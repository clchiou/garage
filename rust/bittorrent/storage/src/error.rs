use std::io;
use std::path::PathBuf;

use snafu::prelude::*;

use bittorrent_base::{BlockDesc, BlockOffset};

#[derive(Clone, Debug, Eq, PartialEq, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    ExpectNonEmptyFile,
    ExpectNonEmptyFileList,

    #[snafu(display("invalid block offset: {offset:?}"))]
    InvalidBlockOffset {
        offset: BlockOffset,
    },
    #[snafu(display("invalid block desc: {desc:?}"))]
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
