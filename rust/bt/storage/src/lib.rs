#![feature(file_lock)]
#![feature(try_blocks)]
#![cfg_attr(test, feature(assert_matches))]
#![cfg_attr(test, feature(iterator_try_collect))]

mod error;
mod metadata_db;
mod storage_dir;
mod torrent;

use std::fs::{self, File, OpenOptions};
use std::io::{self, ErrorKind};
use std::os::fd::AsRawFd;
use std::path::Path;
use std::sync::Arc;

use bytes::Bytes;
use snafu::prelude::*;

use bt_base::InfoHash;
use bt_metainfo::{Info, Metainfo};

use crate::error::{IoSnafu, LayoutSnafu};
use crate::metadata_db::MetadataDb;
use crate::storage_dir::StorageDir;

pub use crate::error::Error;

#[derive(Debug)]
pub struct Storage {
    storage_dir: Arc<StorageDir>,
    // Implementer's Notes: It might seem like a clever idea to store metadata in a torrent file's
    // `xattr`, but we decided not to adopt this approach because `xattr` has a size limit --
    // usually 64 KB -- and we are concerned that it might have additional obscure limitations.
    metadata_db: MetadataDb,
}

pub use crate::torrent::{Torrent, TorrentFile};

impl Storage {
    pub fn open<P>(storage_dir: P) -> Result<Self, Error>
    where
        P: AsRef<Path>,
    {
        let storage_dir = Arc::new(StorageDir::open(storage_dir)?);
        let metadata_db = MetadataDb::open(storage_dir.metadata_db_path())?;

        storage_dir.cleanup(metadata_db.list()?)?;

        Ok(Self {
            storage_dir,
            metadata_db,
        })
    }

    pub fn list(&self) -> Result<Vec<InfoHash>, Error> {
        self.metadata_db.list()
    }

    pub fn get_metainfo(&self, info_hash: InfoHash) -> Result<Option<Metainfo>, Error> {
        self.metadata_db.get_metainfo(info_hash)
    }

    pub fn get_metainfo_blob(&self, info_hash: InfoHash) -> Result<Option<Bytes>, Error> {
        self.metadata_db.get_metainfo_blob(info_hash)
    }

    pub fn get_info(&self, info_hash: InfoHash) -> Result<Option<Info>, Error> {
        self.metadata_db.get_info(info_hash)
    }

    pub fn get_info_blob(&self, info_hash: InfoHash) -> Result<Option<Bytes>, Error> {
        self.metadata_db.get_info_blob(info_hash)
    }

    pub fn insert_metainfo(&self, metainfo: Metainfo) -> Result<bool, Error> {
        self.metadata_db.insert_metainfo(metainfo)
    }

    pub fn insert_metainfo_blob(&self, metainfo_blob: &[u8]) -> Result<bool, Error> {
        self.metadata_db.insert_metainfo_blob(metainfo_blob)
    }

    pub fn insert_info(&self, info: Info) -> Result<bool, Error> {
        self.metadata_db.insert_info(info)
    }

    pub fn insert_info_blob(&self, info_blob: &[u8]) -> Result<bool, Error> {
        self.metadata_db.insert_info_blob(info_blob)
    }

    pub fn open_torrent(&self, info_hash: InfoHash) -> Result<Option<Torrent>, Error> {
        let (torrent_path, guard) = self.storage_dir.lock(info_hash.clone())?;

        let Some(info) = self.get_info(info_hash)? else {
            return Ok(None);
        };

        let layout = info.layout().context(LayoutSnafu)?;

        let torrent = open_torrent(torrent_path, layout.size()).context(IoSnafu)?;

        Ok(Some(Torrent::new(torrent, layout, info, guard)))
    }

    pub fn remove_torrent(&self, info_hash: InfoHash) -> Result<bool, Error> {
        let (torrent_path, _guard) = self.storage_dir.lock(info_hash.clone())?;

        let removed = self.metadata_db.remove(info_hash)?;

        fs::remove_file(&torrent_path)
            .or_else(|error| {
                if error.kind() == ErrorKind::NotFound {
                    return Ok(());
                }

                if !fs::exists(&torrent_path).unwrap_or_else(|check_exist_error| {
                    tracing::debug!(%check_exist_error, "remove_torrent");
                    true
                }) {
                    // `fs::remove_file` may return a [false error] when `torrent_path` does not
                    // exist.
                    // [false error]: https://doc.rust-lang.org/std/fs/fn.remove_file.html#errors
                    tracing::debug!(%error, "remove_torrent: succeed with error");
                    return Ok(());
                }

                Err(error)
            })
            .context(IoSnafu)?;

        Ok(removed)
    }
}

fn open_torrent<P>(path: P, size: u64) -> Result<File, io::Error>
where
    P: AsRef<Path>,
{
    let torrent = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)?;

    fallocate(&torrent, size)?;

    Ok(torrent)
}

fn fallocate<F>(file: &F, size: u64) -> Result<(), io::Error>
where
    F: AsRawFd,
{
    // TODO: `fallocate` is Linux-specific.  Should we use `posix_fallocate` instead?
    if unsafe { libc::fallocate64(file.as_raw_fd(), 0, 0, size.try_into().expect("size")) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

#[cfg(test)]
mod testing {
    use std::fs;
    use std::io::Error;
    use std::path::Path;

    use md5::{Digest, Md5};

    use bt_base::{InfoHash, Md5Hash};
    use bt_bencode::bencode;
    use bt_metainfo::{Info, Metainfo};

    pub(crate) fn mock_metainfo(info: &Info) -> Metainfo {
        bt_bencode::from_buf(
            bt_bencode::to_bytes(&bencode!({
                b"info": bt_bencode::to_value(info).unwrap(),
            }))
            .unwrap(),
        )
        .unwrap()
    }

    pub(crate) fn mock_info(
        name: &str,
        content: &[u8],
        piece_length: usize,
        files: &[(&[&str], usize)],
    ) -> Info {
        fn md5_digest(data: &[u8]) -> String {
            Md5Hash::from(<[u8; 16]>::from(Md5::digest(data))).to_string()
        }

        fn to_i64(x: usize) -> i64 {
            x.try_into().unwrap()
        }

        let mut pieces = Vec::new();
        for piece in content.chunks(piece_length) {
            pieces.extend_from_slice(InfoHash::digest(piece).as_ref());
        }

        if files.is_empty() {
            bt_bencode::from_value(bencode!({
                b"name": name.as_bytes(),
                b"piece length": to_i64(piece_length),
                b"pieces": pieces,

                b"length": to_i64(content.len()),
                b"md5sum": md5_digest(content).as_bytes(),
            }))
        } else {
            // Sanity check.
            assert_eq!(
                files.iter().map(|(_, length)| *length).sum::<usize>(),
                content.len(),
            );

            let files = files
                .iter()
                .scan(0, |acc, (path, length)| {
                    let offset = *acc;
                    *acc += length;
                    Some(bencode!({
                        b"path": bt_bencode::to_value(path).unwrap(),
                        b"length": to_i64(*length),
                        b"md5sum": md5_digest(&content[offset..*acc]).as_bytes(),
                    }))
                })
                .collect::<Vec<_>>();

            bt_bencode::from_value(bencode!({
                b"name": name.as_bytes(),
                b"piece length": to_i64(piece_length),
                b"pieces": pieces,

                b"files": bt_bencode::to_value(&files).unwrap(),
            }))
        }
        .unwrap()
    }

    pub(crate) fn assert_dir(dir: &Path, expect: &[&Path]) {
        let mut paths = fs::read_dir(dir)
            .unwrap()
            .map(|entry| Ok::<_, Error>(entry?.path()))
            .try_collect::<Vec<_>>()
            .unwrap();
        paths.sort();

        let mut expect = expect.to_vec();
        expect.sort();

        assert_eq!(paths, expect);
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use crate::testing::{assert_dir, mock_info};

    use super::*;

    #[test]
    fn open_torrent() {
        let info = mock_info("foo", b"bar", 1, &[]);
        let info_hash = InfoHash::digest(&bt_bencode::to_bytes(&info).unwrap());

        let tempdir = tempfile::tempdir().unwrap();
        let dir = tempdir.path();
        let metadata_db = dir.join("metadata.db");
        let torrent = dir.join(info_hash.to_string());

        let storage = Storage::open(dir).unwrap();
        assert_dir(dir, &[&metadata_db]);

        for _ in 0..3 {
            assert_matches!(storage.open_torrent(info_hash.clone()), Ok(None));
            assert_dir(dir, &[&metadata_db]);
        }

        assert_matches!(storage.insert_info(info), Ok(true));
        assert_dir(dir, &[&metadata_db]);

        let t = storage.open_torrent(info_hash.clone()).unwrap().unwrap();
        assert_dir(dir, &[&metadata_db, &torrent]);

        assert_matches!(
            storage.open_torrent(info_hash.clone()),
            Err(Error::Lock { path }) if path == torrent,
        );
        assert_dir(dir, &[&metadata_db, &torrent]);

        drop(t);
        assert_matches!(storage.open_torrent(info_hash.clone()), Ok(Some(_)));
        assert_dir(dir, &[&metadata_db, &torrent]);
    }

    #[test]
    fn remove_torrent() {
        let info = mock_info("foo", b"bar", 1, &[]);
        let info_hash = InfoHash::digest(&bt_bencode::to_bytes(&info).unwrap());

        let tempdir = tempfile::tempdir().unwrap();
        let dir = tempdir.path();
        let metadata_db = dir.join("metadata.db");
        let torrent = dir.join(info_hash.to_string());

        let storage = Storage::open(dir).unwrap();
        assert_matches!(storage.insert_info(info), Ok(true));
        let t = storage.open_torrent(info_hash.clone()).unwrap().unwrap();
        assert_dir(dir, &[&metadata_db, &torrent]);

        assert_matches!(
            storage.remove_torrent(info_hash.clone()),
            Err(Error::Lock { path }) if path == torrent,
        );
        assert_matches!(
            storage.list(),
            Ok(info_hashes) if info_hashes == &[info_hash.clone()],
        );
        assert_dir(dir, &[&metadata_db, &torrent]);

        drop(t);
        assert_matches!(storage.remove_torrent(info_hash.clone()), Ok(true));
        assert_matches!(storage.list(), Ok(info_hashes) if info_hashes == &[]);
        assert_dir(dir, &[&metadata_db]);
        for _ in 0..3 {
            assert_matches!(storage.remove_torrent(info_hash.clone()), Ok(false));
            assert_matches!(storage.list(), Ok(info_hashes) if info_hashes == &[]);
            assert_dir(dir, &[&metadata_db]);
        }
    }
}
