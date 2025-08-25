use std::io::{self, Error, Write};

use clap::Args;
use serde::Serialize;

use bt_base::{InfoHash, Md5Hash};
use bt_metainfo::Info;
use bt_storage::{Storage, Torrent};

use crate::text::Format;

use super::StorageDir;

#[derive(Args, Debug)]
#[command(about = "List torrent(s)")]
pub(crate) struct LsCommand {
    #[command(flatten)]
    storage_dir: StorageDir,

    #[arg(short, long, help = "Enable longer output")]
    long: bool,

    #[arg(long, value_enum, default_value_t = Format::Debug, help = "Output format")]
    format: Format,

    #[arg(requires = "EntityType")]
    info_hash: Option<InfoHash>,

    #[command(flatten)]
    entity_type: EntityType,
}

// TODO: Switch this to an enum once [#2616] is fixed.
// [#2616]: https://github.com/clap-rs/clap/issues/2621
#[derive(Args, Debug)]
#[group(multiple = false, requires = "info_hash")]
struct EntityType {
    #[arg(short, long, help = "List pieces of a torrent")]
    piece: bool,

    #[arg(short, long, value_name = "INDEX", help = "List file(s) of a torrent")]
    file: Option<Option<usize>>,
}

#[derive(Debug, Serialize)]
struct Piece {
    hash: String,
    verify: bool,
}

#[derive(Debug, Serialize)]
struct File {
    path: String,
    size: u64,
    md5sum: Option<Md5Hash>,
    verify: Option<bool>,
}

impl LsCommand {
    pub(crate) fn run(&self) -> Result<(), Error> {
        let storage = self.storage_dir.open(false)?;
        let output = io::stdout();
        match self.info_hash.clone() {
            None => self.ls_torrents(storage, output),
            Some(info_hash) => match (self.entity_type.piece, self.entity_type.file) {
                (true, None) => self.ls_pieces(storage, info_hash, output),
                (false, Some(None)) => self.ls_files(storage, info_hash, output),
                (false, Some(Some(file_index))) => {
                    self.ls_file(storage, info_hash, file_index, output)
                }
                _ => unreachable!(),
            },
        }
    }

    fn ls_torrents<W>(&self, storage: Storage, output: W) -> Result<(), Error>
    where
        W: Write,
    {
        let info_hashes = storage.list()?;
        if !self.long {
            return self.format.write(info_hashes, output);
        }

        #[derive(Debug, Serialize)]
        struct Torrent {
            info_hash: InfoHash,
            name: String,
            size: u64,
            piece_length: u64,
            num_pieces: usize,
            num_files: usize,
        }

        let torrents = info_hashes
            .into_iter()
            .map(|info_hash| {
                storage.get_info(info_hash.clone()).map(|info| {
                    let info = info.expect("info");
                    Torrent {
                        info_hash,
                        name: info.name().to_string(),
                        size: info.length(),
                        piece_length: info.piece_length(),
                        num_pieces: info.pieces().len(),
                        num_files: info.len(),
                    }
                })
            })
            .try_collect::<Vec<_>>()?;
        self.format.write(torrents, output)
    }

    fn ls_pieces<W>(&self, storage: Storage, info_hash: InfoHash, output: W) -> Result<(), Error>
    where
        W: Write,
    {
        let Some(info) = storage.get_info(info_hash.clone())? else {
            return Ok(());
        };

        let piece_hashes = info
            .pieces()
            .iter()
            .map(|piece_hash| piece_hash.to_string())
            .collect::<Vec<_>>();
        if !self.long {
            return self.format.write(piece_hashes, output);
        }

        let bitfield = storage.open_torrent(info_hash)?.expect("torrent").scan()?;
        assert_eq!(piece_hashes.len(), bitfield.len());
        let pieces = piece_hashes
            .into_iter()
            .zip(bitfield.iter().by_vals())
            .map(|(hash, verify)| Piece { hash, verify })
            .collect::<Vec<_>>();
        self.format.write(pieces, output)
    }

    fn ls_files<W>(&self, storage: Storage, info_hash: InfoHash, output: W) -> Result<(), Error>
    where
        W: Write,
    {
        let Some(info) = storage.get_info(info_hash.clone())? else {
            return Ok(());
        };

        if !self.long {
            let paths = (0..info.len()).map(|i| path(&info, i)).collect::<Vec<_>>();
            return self.format.write(paths, output);
        }

        let mut torrent = storage.open_torrent(info_hash)?.expect("torrent");
        let files = (0..info.len())
            .map(|i| File::new(&info, &mut torrent, i))
            .try_collect::<Vec<_>>()?;
        self.format.write(files, output)
    }

    fn ls_file<W>(
        &self,
        storage: Storage,
        info_hash: InfoHash,
        file_index: usize,
        output: W,
    ) -> Result<(), Error>
    where
        W: Write,
    {
        let Some(info) = storage.get_info(info_hash.clone())? else {
            return Ok(());
        };

        if file_index >= info.len() {
            return Err(Error::other(format!(
                "file index out of range: {file_index}"
            )));
        }

        let mut torrent = storage.open_torrent(info_hash)?.expect("torrent");
        let file = File::new(&info, &mut torrent, file_index)?;
        if !self.long {
            return self.format.write(file, output);
        }

        let mut torrent_file = torrent.get(file_index);
        let index_range = torrent_file.index_range();
        let bitfield = torrent_file.scan()?;
        let piece_hashes = info.pieces();
        let pieces = index_range
            .map(|index| {
                piece_hashes
                    .get(index.0.try_into().expect("usize"))
                    .expect("piece")
                    .to_string()
            })
            .zip(bitfield.iter().by_vals())
            .map(|(hash, verify)| Piece { hash, verify })
            .collect::<Vec<_>>();
        self.format.write((file, pieces), output)
    }
}

impl File {
    fn new(info: &Info, torrent: &mut Torrent, file_index: usize) -> Result<Self, Error> {
        let file = info.file(file_index);
        Ok(Self {
            path: path(info, file_index),
            size: file.length,
            md5sum: file.md5sum,
            verify: torrent.get(file_index).verify_md5sum()?,
        })
    }
}

fn path(info: &Info, i: usize) -> String {
    [info.name()]
        .into_iter()
        .chain(info.file(i).path.iter().map(|p| p.as_str()))
        .intersperse("/")
        .collect()
}
