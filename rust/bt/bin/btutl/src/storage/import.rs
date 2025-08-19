use std::io::{self, Error, Read};
use std::os::fd::AsFd;
use std::panic;
use std::thread;

use bytes::Bytes;
use clap::Args;
use nix::fcntl::{OFlag, SpliceFFlags, splice};
use nix::unistd::pipe2;

use bt_base::{BlockRange, InfoHash};
use bt_metainfo::Info;
use bt_storage::{Storage, Torrent};

use super::{PieceHash, StorageDir};

#[derive(Args, Debug)]
#[command(about = "Import data into the torrent storage")]
pub(crate) struct ImportCommand {
    #[command(flatten)]
    storage_dir: StorageDir,

    #[command(flatten)]
    import: Import,

    #[command(flatten)]
    entity_type: Option<EntityType>,

    // Add an explicit `conflicts_with` rule because `clap` does not produce an error for
    // `--file <index> --force`.
    #[arg(
        long,
        conflicts_with = "file",
        requires = "piece",
        help = "Ignore failed piece hash verification"
    )]
    force: bool,
}

// TODO: Switch this to an enum once [#2616] is fixed.
// [#2616]: https://github.com/clap-rs/clap/issues/2621
#[derive(Args, Debug)]
#[group(multiple = false)]
struct Import {
    #[arg(long, help = "Create a new torrent from metainfo")]
    metainfo: bool,

    #[arg(long, help = "Create a new torrent from info")]
    info: bool,

    #[arg(requires = "EntityType")]
    info_hash: Option<InfoHash>,
}

// TODO: Switch this to an enum once [#2616] is fixed.
// [#2616]: https://github.com/clap-rs/clap/issues/2621
#[derive(Args, Debug)]
#[group(multiple = false, requires = "info_hash")]
struct EntityType {
    #[arg(
        short,
        long,
        value_name = "HASH",
        help = "Import a piece into a torrent"
    )]
    piece: Option<Option<PieceHash>>,

    #[arg(
        short,
        long,
        value_name = "INDEX",
        help = "Import a file into a torrent"
    )]
    file: Option<usize>,
}

impl ImportCommand {
    pub(crate) fn run(&self) -> Result<(), Error> {
        let storage = self.storage_dir.open(true)?;
        let input = io::stdin();
        if self.import.metainfo {
            self.import_metainfo(storage, input)
        } else if self.import.info {
            self.import_info(storage, input)
        } else if let Some(info_hash) = self.import.info_hash.clone() {
            let Some(info) = storage.get_info(info_hash.clone())? else {
                return Err(Error::other(format!("torrent not found: {info_hash}")));
            };
            let torrent = storage.open_torrent(info_hash)?.expect("torrent");
            let entity_type = self.entity_type.as_ref().expect("entity_type");
            match (entity_type.piece.clone(), entity_type.file) {
                (Some(piece_hash), None) => self.import_piece(info, torrent, piece_hash, input),
                (None, Some(file_index)) => self.import_file(torrent, file_index, input),
                _ => unreachable!(),
            }
        } else {
            // Default to `--metainfo`.
            self.import_metainfo(storage, input)
        }
    }

    fn import_metainfo<R>(&self, storage: Storage, input: R) -> Result<(), Error>
    where
        R: Read,
    {
        storage.insert_metainfo_blob(&read_to_end(input)?)?;
        Ok(())
    }

    fn import_info<R>(&self, storage: Storage, input: R) -> Result<(), Error>
    where
        R: Read,
    {
        storage.insert_info_blob(&read_to_end(input)?)?;
        Ok(())
    }

    fn import_piece<R>(
        &self,
        info: Info,
        mut torrent: Torrent,
        piece_hash: Option<PieceHash>,
        input: R,
    ) -> Result<(), Error>
    where
        R: Read,
    {
        let index;
        let size;
        let piece;
        match piece_hash {
            Some(piece_hash) => {
                (index, size) = super::piece_index_and_size(&info, piece_hash.clone())?;
                piece = read_exact(input, size)?;

                let actual = PieceHash::digest(&piece);
                if actual != piece_hash {
                    if self.force {
                        tracing::warn!(%actual, expect = %piece_hash, "piece hash does not match");
                    } else {
                        return Err(Error::other(format!(
                            "piece hash does not match: {actual} != {piece_hash}"
                        )));
                    }
                }
            }
            None => {
                piece = read_to_end(input.take(info.piece_length()))?;
                (index, size) = super::piece_index_and_size(&info, PieceHash::digest(&piece))?;
            }
        }
        Ok(torrent.write(BlockRange(index, 0, size), &piece)?)
    }

    fn import_file<R>(&self, mut torrent: Torrent, file_index: usize, input: R) -> Result<(), Error>
    where
        R: AsFd + Send + 'static,
    {
        let size = torrent.prepare_splice(file_index)?;

        //
        // NOTE: We add a pipe so that the user can import from regular files.  Note that they
        // cannot import from device files, such as `/dev/zero`, unless they are running a newer
        // kernel [1].  In such cases, they need to add an extra pipe, for example:
        // ```
        // cat /dev/zero | ...
        // ```
        //
        // [1]: https://github.com/torvalds/linux/commit/1b057bd800c3ea0c926191d7950cd2365eddc9bb
        //
        let (r, w) = pipe2(OFlag::O_CLOEXEC)?;
        let h1 = thread::spawn(move || splice_all(input, w, size));
        let h2 = thread::spawn(move || splice_all(r, torrent.as_mut(), size));
        let r1 = match h1.join() {
            Ok(result) => result,
            Err(error) => panic::resume_unwind(error),
        };
        let r2 = match h2.join() {
            Ok(result) => result,
            Err(error) => panic::resume_unwind(error),
        };
        let actual = r1.and(r2)?;

        if actual == size {
            Ok(())
        } else {
            Err(Error::other(format!(
                "import less then expected: {actual} != {size}"
            )))
        }
    }
}

fn read_to_end<R>(mut reader: R) -> Result<Bytes, Error>
where
    R: Read,
{
    let mut data = Vec::new();
    reader.read_to_end(&mut data)?;
    Ok(data.into())
}

fn read_exact<R>(mut reader: R, size: u64) -> Result<Bytes, Error>
where
    R: Read,
{
    let mut data = vec![0u8; usize::try_from(size).expect("usize")];
    reader.read_exact(&mut data)?;
    Ok(data.into())
}

fn splice_all<I, O>(input: I, output: O, size: usize) -> Result<usize, Error>
where
    I: AsFd,
    O: AsFd,
{
    const FLAGS: SpliceFFlags = SpliceFFlags::SPLICE_F_MOVE;

    let mut count = size;
    while count > 0 {
        match splice(&input, None, &output, None, count, FLAGS)? {
            0 => break,
            n => count -= n,
        }
    }
    Ok(size - count)
}
