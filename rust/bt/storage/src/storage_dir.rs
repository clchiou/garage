use std::collections::HashSet;
use std::fs::{self, File, TryLockError};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, Weak};

use snafu::prelude::*;

use g1_base::sync::MutexExt;

use bt_base::InfoHash;

use crate::error::{Error, IoSnafu};

#[derive(Debug)]
pub(crate) struct StorageDir {
    storage_dir: PathBuf,
    locked: Mutex<HashSet<InfoHash>>,
    _lock: File,
}

#[derive(Debug)]
pub(crate) struct TorrentGuard {
    storage_dir: Weak<StorageDir>,
    info_hash: InfoHash,
}

impl Drop for TorrentGuard {
    fn drop(&mut self) {
        if let Some(storage_dir) = self.storage_dir.upgrade() {
            storage_dir.unlock(&self.info_hash);
        }
    }
}

const METADATA_DB: &str = "metadata.db";

impl StorageDir {
    pub(crate) fn open<P>(storage_dir: P) -> Result<Self, Error>
    where
        P: AsRef<Path>,
    {
        let result: Result<_, _> = try {
            // `canonicalize` errors when the target does not exist, which is what we want.
            let storage_dir = storage_dir.as_ref().canonicalize()?;
            tracing::info!(storage = %storage_dir.display(), "open");

            let lock = File::open(&storage_dir)?;
            match lock.try_lock() {
                Ok(()) => {}
                Err(TryLockError::Error(error)) => Err(error)?,
                Err(TryLockError::WouldBlock) => return Err(Error::Lock { path: storage_dir }),
            }

            Self {
                storage_dir,
                locked: Mutex::new(HashSet::new()),
                _lock: lock,
            }
        };
        result.context(IoSnafu)
    }

    pub(crate) fn metadata_db_path(&self) -> PathBuf {
        self.storage_dir.join(METADATA_DB)
    }

    fn torrent_path(&self, info_hash: &InfoHash) -> PathBuf {
        self.storage_dir.join(info_hash.to_string())
    }

    pub(crate) fn cleanup(&self, info_hashes: Vec<InfoHash>) -> Result<(), Error> {
        let result: Result<_, _> = try {
            // I am not sure, but it feels wrong to remove files while iterating through the
            // directory.
            let mut to_remove = Vec::new();
            for entry in fs::read_dir(&self.storage_dir)? {
                let entry = entry?;
                let path = entry.path();

                if !entry.file_type()?.is_file() {
                    tracing::info!(path = %path.display(), "cleanup: skip non-file");
                    continue;
                }

                let name = path.file_name().expect("file_name");

                if name == METADATA_DB {
                    continue;
                }

                let Some(info_hash) = name.to_str().and_then(|name| name.parse().ok()) else {
                    tracing::info!(path = %path.display(), "cleanup: skip unrecognizable file");
                    continue;
                };

                if !info_hashes.contains(&info_hash) {
                    to_remove.push(path);
                }
            }

            for path in to_remove {
                tracing::info!(path = %path.display(), "cleanup");
                fs::remove_file(&path)?;
            }
        };
        result.context(IoSnafu)
    }

    pub(crate) fn lock(
        self: &Arc<Self>,
        info_hash: InfoHash,
    ) -> Result<(PathBuf, TorrentGuard), Error> {
        let mut locked = self.locked.must_lock();
        let path = self.torrent_path(&info_hash);
        if locked.insert(info_hash.clone()) {
            Ok((
                path,
                TorrentGuard {
                    storage_dir: Arc::downgrade(self),
                    info_hash,
                },
            ))
        } else {
            Err(Error::Lock { path })
        }
    }

    fn unlock(&self, info_hash: &InfoHash) {
        assert!(self.locked.must_lock().remove(info_hash));
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;

    use crate::testing::assert_dir;

    use super::*;

    #[test]
    fn dir_lock() {
        let tempdir = tempfile::tempdir().unwrap();
        let dir = tempdir.path();

        let storage_dir = StorageDir::open(dir).unwrap();

        assert_matches!(
            StorageDir::open(dir),
            Err(Error::Lock { path }) if path == tempdir.path(),
        );

        drop(storage_dir);
        assert_matches!(StorageDir::open(dir), Ok(_));
    }

    #[test]
    fn cleanup() {
        let x00 = InfoHash::from([0x00; 20]);
        let x01 = InfoHash::from([0x01; 20]);
        let x02 = InfoHash::from([0x02; 20]);

        let tempdir = tempfile::tempdir().unwrap();
        let dir = tempdir.path();
        let metadata_db = dir.join("metadata.db");
        let t00 = dir.join(x00.to_string());
        let t01 = dir.join(x01.to_string());
        let t02 = dir.join(x02.to_string());
        let other = dir.join("other");

        fs::write(&metadata_db, b"").unwrap();
        fs::write(&t00, b"").unwrap();
        fs::write(&t01, b"").unwrap();
        fs::create_dir(&t02).unwrap();
        fs::write(&other, b"").unwrap();
        assert_dir(dir, &[&metadata_db, &t00, &t01, &t02, &other]);

        let storage_dir = Arc::new(StorageDir::open(dir).unwrap());
        assert_dir(dir, &[&metadata_db, &t00, &t01, &t02, &other]);

        assert_matches!(storage_dir.cleanup(vec![x00]), Ok(()));
        assert_dir(dir, &[&metadata_db, &t00, &t02, &other]);
    }

    #[test]
    fn lock() {
        let info_hash = InfoHash::from([0x00; 20]);

        let tempdir = tempfile::tempdir().unwrap();
        let dir = tempdir.path();
        let expect_path = dir.join(info_hash.to_string());

        let storage_dir = Arc::new(StorageDir::open(dir).unwrap());

        let (path, guard) = storage_dir.lock(info_hash.clone()).unwrap();
        assert_eq!(path, expect_path);

        assert_matches!(
            storage_dir.lock(info_hash.clone()),
            Err(Error::Lock { path }) if path == expect_path,
        );

        drop(guard);
        assert_matches!(storage_dir.lock(info_hash.clone()), Ok(_));
    }
}
