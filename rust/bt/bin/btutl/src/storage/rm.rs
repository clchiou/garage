use std::io::Error;

use clap::Args;

use bt_base::InfoHash;

use super::StorageDir;

#[derive(Args, Debug)]
#[command(about = "Remove a torrent")]
pub(crate) struct RmCommand {
    #[command(flatten)]
    storage_dir: StorageDir,

    info_hash: InfoHash,
}

impl RmCommand {
    pub(crate) fn run(&self) -> Result<(), Error> {
        let storage = self.storage_dir.open(false)?;
        storage.remove_torrent(self.info_hash.clone())?;
        Ok(())
    }
}
