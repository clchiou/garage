use std::path::{Path, PathBuf};

use bittorrent_metainfo::{Info, Mode};

use crate::{coord::CoordSys, error, io, PieceHash};

pub(crate) fn new_piece_hashes(info: &Info) -> Vec<PieceHash> {
    info.pieces
        .iter()
        .map(|piece_hash| (*piece_hash).try_into().unwrap())
        .collect()
}

pub(crate) fn new_coord_sys(
    info: &Info,
    file_sizes: impl Iterator<Item = u64>,
) -> Result<CoordSys, error::Error> {
    CoordSys::new(info.pieces.len(), info.piece_length, file_sizes)
}

pub(crate) fn new_paths(
    info: &Info,
    torrent_dir: &Path,
) -> Result<Vec<(PathBuf, u64)>, error::Error> {
    let mut paths = Vec::new();
    let torrent_dir = io::expect_dir(torrent_dir)?;
    match info.mode {
        Mode::SingleFile { length, .. } => {
            paths.push((torrent_dir.join(io::expect_relpath(info.name)?), length));
        }
        Mode::MultiFile { ref files } => {
            let info_name = io::expect_relpath(info.name)?;
            for file in files {
                paths.push((
                    [Ok(torrent_dir), Ok(info_name)]
                        .into_iter()
                        .chain(file.path.iter().copied().map(io::expect_relpath))
                        .try_collect()?,
                    file.length,
                ));
            }
        }
    }
    Ok(paths)
}
