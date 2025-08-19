use std::io;
use std::path::PathBuf;

use bytes::Bytes;
use snafu::prelude::*;

use bt_base::{BlockRange, PieceIndex};
use bt_metainfo::Insane;

#[derive(Debug, Snafu)]
#[snafu(visibility(pub(crate)))]
pub enum Error {
    #[snafu(display("bencode error: {source}"))]
    Bencode { source: bt_bencode::error::Error },

    #[snafu(display("buffer overflow: {len} < {size}"))]
    BufferOverflow { len: usize, size: usize },

    #[snafu(display("invalid block range: {range:?}"))]
    InvalidBlockRange { range: BlockRange },
    #[snafu(display("invalid piece index: {index:?}"))]
    InvalidPieceIndex { index: PieceIndex },

    #[snafu(display("io error: {source}"))]
    Io { source: io::Error },

    #[snafu(display("torrent layout error: {source}"))]
    Layout { source: bt_base::layout::Error },

    #[snafu(display("already locked: {}", path.display()))]
    Lock { path: PathBuf },

    #[snafu(display("metainfo or info sanity check fail: {source}"))]
    MetadataInsane { source: Insane },
    #[snafu(display("metainfo or info trailing data: \"{}\"", data.escape_ascii()))]
    MetadataTrailingData { data: Bytes },

    #[snafu(display("sqlite error: {source}"))]
    Sqlite { source: rusqlite::Error },
}

impl From<Error> for io::Error {
    fn from(error: Error) -> Self {
        match error {
            Error::Io { source } => source,
            _ => io::Error::other(error),
        }
    }
}
