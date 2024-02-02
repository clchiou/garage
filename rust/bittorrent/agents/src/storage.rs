use std::io::Error;
use std::path::PathBuf;

use bittorrent_base::Dimension;
use bittorrent_metainfo::Info;
use bittorrent_storage::{file, single};
use bittorrent_transceiver::DynStorage;

#[derive(Debug)]
pub enum StorageOpen {
    File(PathBuf),
    Single(PathBuf),
}

impl StorageOpen {
    pub(crate) async fn open(&self, info: &Info<'_>, dim: Dimension) -> Result<DynStorage, Error> {
        Ok(match self {
            Self::File(torrent_dir) => Box::new(file::Storage::open(info, dim, torrent_dir).await?),
            Self::Single(torrent_dir) => {
                Box::new(single::Storage::open(info, dim, torrent_dir).await?)
            }
        })
    }
}
