mod export;
mod import;
mod ls;
mod rm;

use std::fs;
use std::io::Error;
use std::path::PathBuf;

use clap::Args;

use bt_base::{InfoHash, PieceIndex};
use bt_metainfo::Info;
use bt_storage::Storage;

pub(crate) use self::export::ExportCommand;
pub(crate) use self::import::ImportCommand;
pub(crate) use self::ls::LsCommand;
pub(crate) use self::rm::RmCommand;

// TODO: We use `InfoHash` as a substitute for an owned `PieceHash` at the moment.
type PieceHash = InfoHash;

#[derive(Args, Debug)]
pub(crate) struct StorageDir {
    #[arg(help = "Torrent storage directory")]
    dir: PathBuf,
}

impl StorageDir {
    pub(crate) fn open(&self, create: bool) -> Result<Storage, Error> {
        if create {
            fs::create_dir_all(&self.dir)?;
        }
        Ok(Storage::open(&self.dir)?)
    }
}

fn piece_index_and_size(info: &Info, piece_hash: PieceHash) -> Result<(PieceIndex, u64), Error> {
    let index = match info
        .pieces()
        .iter()
        .position(|hash| hash.as_ref() as &[u8] == piece_hash.as_ref() as &[u8])
    {
        Some(index) => PieceIndex(index.try_into().expect("piece index")),
        None => return Err(Error::other(format!("piece hash not found: {piece_hash}"))),
    };
    let size = info.layout().map_err(Error::other)?.piece_size(index);
    Ok((index, size))
}
