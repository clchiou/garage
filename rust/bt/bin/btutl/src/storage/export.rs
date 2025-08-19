use std::io::{self, Error, Write};
use std::os::fd::AsFd;

use clap::Args;
use nix::sys::sendfile::sendfile64;

use bt_base::{BlockRange, InfoHash};
use bt_storage::Storage;

use super::{PieceHash, StorageDir};

#[derive(Args, Debug)]
#[command(about = "Export data from the torrent storage")]
pub(crate) struct ExportCommand {
    #[command(flatten)]
    storage_dir: StorageDir,

    #[command(flatten)]
    export: Export,

    info_hash: InfoHash,
}

// TODO: Switch this to an enum once [#2616] is fixed.
// [#2616]: https://github.com/clap-rs/clap/issues/2621
#[derive(Args, Debug)]
#[group(multiple = false)]
struct Export {
    #[arg(long, help = "Export a torrent's metainfo")]
    metainfo: bool,

    #[arg(long, help = "Export a torrent's info")]
    info: bool,

    #[arg(
        short,
        long,
        value_name = "HASH",
        help = "Export a piece from a torrent"
    )]
    piece: Option<PieceHash>,

    #[arg(
        short,
        long,
        value_name = "INDEX",
        help = "Export a file from a torrent"
    )]
    file: Option<usize>,
}

impl ExportCommand {
    pub(crate) fn run(&self) -> Result<(), Error> {
        let storage = self.storage_dir.open(false)?;
        let output = io::stdout();
        if self.export.metainfo {
            self.export_metainfo(storage, output)
        } else if self.export.info {
            self.export_info(storage, output)
        } else if let Some(piece_hash) = self.export.piece.clone() {
            self.export_piece(storage, piece_hash, output)
        } else if let Some(file_index) = self.export.file {
            self.export_file(storage, file_index, output)
        } else {
            // Default to `--metainfo`.
            self.export_metainfo(storage, output)
        }
    }

    fn not_found_error(&self) -> Error {
        Error::other(format!("torrent not found: {}", self.info_hash))
    }

    fn export_metainfo<W>(&self, storage: Storage, mut output: W) -> Result<(), Error>
    where
        W: Write,
    {
        let Some(metainfo_blob) = storage.get_metainfo_blob(self.info_hash.clone())? else {
            return Err(
                if storage.get_info_blob(self.info_hash.clone())?.is_some() {
                    Error::other(format!("metainfo not stored: {}", self.info_hash))
                } else {
                    self.not_found_error()
                },
            );
        };
        output.write_all(&metainfo_blob)
    }

    fn export_info<W>(&self, storage: Storage, mut output: W) -> Result<(), Error>
    where
        W: Write,
    {
        let Some(info_blob) = storage.get_info_blob(self.info_hash.clone())? else {
            return Err(self.not_found_error());
        };
        output.write_all(&info_blob)
    }

    fn export_piece<W>(
        &self,
        storage: Storage,
        piece_hash: PieceHash,
        mut output: W,
    ) -> Result<(), Error>
    where
        W: Write,
    {
        let Some(info) = storage.get_info(self.info_hash.clone())? else {
            return Err(self.not_found_error());
        };

        let mut torrent = storage
            .open_torrent(self.info_hash.clone())?
            .expect("torrent");

        let (index, size) = super::piece_index_and_size(&info, piece_hash.clone())?;

        let mut buffer = vec![0u8; size.try_into().expect("usize")];
        torrent.read(BlockRange(index, 0, size), &mut buffer)?;

        output.write_all(&buffer)
    }

    fn export_file<W>(&self, storage: Storage, file_index: usize, output: W) -> Result<(), Error>
    where
        W: AsFd,
    {
        let Some(mut torrent) = storage.open_torrent(self.info_hash.clone())? else {
            return Err(self.not_found_error());
        };

        let size = torrent.prepare_splice(file_index)?;
        let actual = sendfile_all(output, torrent.as_mut(), size)?;
        if actual != size {
            tracing::warn!(actual, expect = size, "export less then expected");
        }
        Ok(())
    }
}

// NOTE: `sendfile` uses the opposite input/output argument order compared to `splice`.
fn sendfile_all<O, I>(output: O, input: I, size: usize) -> Result<usize, Error>
where
    O: AsFd,
    I: AsFd,
{
    let mut count = size;
    while count > 0 {
        match sendfile64(&output, &input, None, count)? {
            0 => break,
            n => count -= n,
        }
    }
    Ok(size - count)
}
