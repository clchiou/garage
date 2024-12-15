#![feature(assert_matches)]
#![feature(try_blocks)]

mod blob;
mod hash;
mod map;

mod storage_capnp {
    // TODO: Remove `clippy::needless_lifetimes` after [#522] has been fixed.
    // [#522]: https://github.com/capnproto/capnproto-rust/issues/522
    #![allow(clippy::needless_lifetimes)]
    include!(concat!(env!("OUT_DIR"), "/ddcache/storage_capnp.rs"));
}

use std::cmp::Reverse;
use std::collections::BinaryHeap;
use std::fs::{self, File, OpenOptions};
use std::io::{Error, ErrorKind};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use bytes::Bytes;
use tokio::task;

use g1_base::sync::MutexExt;

use crate::blob::BlobMetadata;
use crate::hash::KeyHash;
use crate::map::{BlobMap, BlobMapBuilder};

//
// Implementer's Notes:
//
// * Currently we do not push "small" I/O operations to `spawn_blocking` because the overhead is
//   probably not worth it.
//
// * Using `spawn_blocking` instead of `tokio::fs::*` has an advantage: it is "atomic" in the sense
//   that we do not have to worry that `tokio::fs::*` is completed but the calling task is
//   cancelled (and thus `guard.commit` is not called).
//

#[derive(Clone, Debug)]
pub struct Storage {
    dir: Arc<Path>,
    map: BlobMap,
    expire_queue: ExpireQueue,
}

#[derive(Clone, Debug)]
struct ExpireQueue(Arc<Mutex<RawExpireQueue>>);

pub(crate) type RawExpireQueue = BinaryHeap<Reverse<(Timestamp, Bytes)>>;

#[derive(Debug)]
pub struct ReadGuard {
    guard: map::ReadGuard,
    path: PathBuf,
}

#[derive(Debug)]
pub struct WriteGuard {
    guard: Option<map::WriteGuard>,
    path: PathBuf,
    truncate: bool,
    new_metadata: Option<BlobMetadata>,
    file: Option<File>, // Use the blocking version of `File` in `Drop::drop`.
    expire_queue: ExpireQueue,
}

#[derive(Debug)]
struct ExpireGuard {
    expire_queue: ExpireQueue,
    rollback: Option<(Timestamp, Bytes)>,
}

pub type RemovedBlobMetadata = (Option<Bytes>, u64, Option<Timestamp>);

pub use g1_chrono::{Timestamp, TimestampExt};

impl Storage {
    pub async fn open(dir: &Path) -> Result<Self, Error> {
        let dir = dir.canonicalize()?;
        // Scanning directories seems to warrant using `spawn_blocking`.
        task::spawn_blocking(move || Self::open_blocking(dir.into()))
            .await
            .unwrap()
    }

    // TODO: We scan the directory and store metadata in memory.  Essentially, we are trading a
    // smaller memory footprint for the ease of implementation and efficiency of `evict`.  We
    // should revisit this tradeoff under production load.
    fn open_blocking(dir: Arc<Path>) -> Result<Self, Error> {
        let mut map = BlobMapBuilder::new();
        for blob_dir in dir.read_dir()? {
            let blob_dir = blob_dir?;
            let Some(blob_dir) = hash::match_blob_dir(&blob_dir)? else {
                tracing::debug!(
                    blob_dir = %blob_dir.path().display(),
                    "skip unrecognizable blob dir",
                );
                continue;
            };
            let mut n = 0;
            for blob in blob_dir.read_dir()? {
                n += 1;
                let blob = blob?;
                let Some(blob) = hash::match_blob(&blob)? else {
                    tracing::debug!(blob = %blob.path().display(), "skip unrecognizable blob");
                    continue;
                };
                if let Err(error) = map.insert(&blob) {
                    tracing::warn!(blob = %blob.display(), %error, "invalid blob");
                    fs::remove_file(&blob)?;
                    n -= 1;
                }
            }
            if n == 0 {
                tracing::debug!(blob_dir = %blob_dir.display(), "remove empty blob dir");
                fs::remove_dir(blob_dir)?;
            }
        }
        let (map, expire_queue) = map.build();
        Ok(Self {
            dir,
            map,
            expire_queue: expire_queue.into(),
        })
    }

    pub fn keys(&self) -> Vec<Bytes> {
        self.map.keys()
    }

    pub fn size(&self) -> u64 {
        self.map.size()
    }

    pub async fn evict(&self, target_size: u64) -> Result<u64, Error> {
        // Evicting cache entries seems to warrant using `spawn_blocking`.
        let this = self.clone();
        task::spawn_blocking(move || this.evict_blocking(target_size))
            .await
            .unwrap()
    }

    fn evict_blocking(&self, target_size: u64) -> Result<u64, Error> {
        while self.size() > target_size {
            if self.try_remove_front()?.is_none() {
                break;
            }
        }
        Ok(self.size())
    }

    pub fn next_expire_at(&self) -> Option<Timestamp> {
        self.expire_queue.peek()
    }

    pub async fn expire(&self, now: Timestamp) -> Result<(), Error> {
        while let Some((expire_at, key)) = self.expire_queue.pop(now) {
            let guard = ExpireGuard::new(self.expire_queue.clone(), expire_at, key.clone());
            if self.remove_expire(key.clone(), now).await?.is_some() {
                tracing::info!(?key, %expire_at, "expire");
            }
            guard.commit();
        }
        Ok(())
    }

    pub async fn read(&self, key: Bytes) -> Option<ReadGuard> {
        self.map.read(key).await.map(|(hash, guard)| ReadGuard {
            guard,
            path: hash.to_path(&self.dir),
        })
    }

    /// Similar to `read`, except that it does not update a cache entry's recency.
    pub async fn peek(&self, key: Bytes) -> Option<ReadGuard> {
        self.map.peek(key).await.map(|(hash, guard)| ReadGuard {
            guard,
            path: hash.to_path(&self.dir),
        })
    }

    pub async fn write(&self, key: Bytes, truncate: bool) -> Result<WriteGuard, Error> {
        const NUM_TRIES: usize = 8;
        for _ in 0..NUM_TRIES {
            match self.map.write(key.clone()).await {
                Ok((hash, guard)) => {
                    return Ok(self.new_write_guard(hash, guard, truncate));
                }
                Err(collision) => {
                    tracing::debug!(?key, ?collision);
                    // We can probably remove the entry by key hash, but the difference is
                    // insignificant.
                    self.remove(collision).await?;
                }
            }
        }
        Err(Error::other(format!(
            "cannot resolve hash collision by replacement: {:?}",
            key,
        )))
    }

    pub fn write_new(&self, key: Bytes) -> Option<WriteGuard> {
        self.map
            .write_new(key)
            .map(|(hash, guard)| self.new_write_guard(hash, guard, true))
    }

    pub fn try_write(&self, key: Bytes, truncate: bool) -> Option<WriteGuard> {
        self.map
            .try_write(key)
            .map(|(hash, guard)| self.new_write_guard(hash, guard, truncate))
    }

    fn new_write_guard(&self, hash: KeyHash, guard: map::WriteGuard, truncate: bool) -> WriteGuard {
        WriteGuard::new(
            guard,
            hash.to_path(&self.dir),
            truncate,
            self.expire_queue.clone(),
        )
    }

    pub async fn remove(&self, key: Bytes) -> Result<Option<RemovedBlobMetadata>, Error> {
        let Some((hash, guard)) = self.map.remove(key).await else {
            return Ok(None);
        };
        let path = hash.to_path(&self.dir);
        Self::do_remove(path, guard)
    }

    pub async fn remove_expire(
        &self,
        key: Bytes,
        now: Timestamp,
    ) -> Result<Option<RemovedBlobMetadata>, Error> {
        let Some((hash, guard)) = self.map.remove(key).await else {
            return Ok(None);
        };
        if !guard.blob_metadata().is_expired(now) {
            return Ok(None);
        }
        let path = hash.to_path(&self.dir);
        Self::do_remove(path, guard)
    }

    pub fn try_remove_front(&self) -> Result<Option<RemovedBlobMetadata>, Error> {
        let Some((hash, guard)) = self.map.try_remove_front() else {
            return Ok(None);
        };
        let path = hash.to_path(&self.dir);
        Self::do_remove(path, guard)
    }

    // We will remove empty directories in `open`.
    fn do_remove(
        path: PathBuf,
        guard: map::RemoveGuard,
    ) -> Result<Option<RemovedBlobMetadata>, Error> {
        // We assume that the file is unchanged on error and does not update the map.
        fs::remove_file(path)?;
        let blob_metadata = guard.blob_metadata();
        let blob_metadata = (
            blob_metadata.metadata.clone(),
            blob_metadata.size,
            blob_metadata.expire_at,
        );
        guard.commit();
        Ok(Some(blob_metadata))
    }
}

impl From<RawExpireQueue> for ExpireQueue {
    fn from(queue: RawExpireQueue) -> Self {
        Self(Arc::new(Mutex::new(queue)))
    }
}

impl ExpireQueue {
    fn peek(&self) -> Option<Timestamp> {
        self.0.must_lock().peek().map(|Reverse((t, _))| *t)
    }

    fn push(&self, expire_at: Timestamp, key: Bytes) {
        self.0.must_lock().push(Reverse((expire_at, key)));
    }

    fn pop(&self, now: Timestamp) -> Option<(Timestamp, Bytes)> {
        let mut queue = self.0.must_lock();
        let Reverse((expire_at, _)) = queue.peek()?;
        if expire_at <= &now {
            Some(queue.pop().unwrap().0)
        } else {
            None
        }
    }
}

impl ReadGuard {
    pub fn metadata(&self) -> Option<Bytes> {
        self.guard.blob_metadata().metadata.clone()
    }

    pub fn size(&self) -> u64 {
        self.guard.blob_metadata().size
    }

    pub fn expire_at(&self) -> Option<Timestamp> {
        self.guard.blob_metadata().expire_at
    }

    pub fn open(&self) -> Result<File, Error> {
        OpenOptions::new().read(true).open(&self.path)
    }
}

impl WriteGuard {
    fn new(
        guard: map::WriteGuard,
        path: PathBuf,
        truncate: bool,
        expire_queue: ExpireQueue,
    ) -> Self {
        Self {
            guard: Some(guard),
            path,
            truncate,
            new_metadata: None,
            file: None,
            expire_queue,
        }
    }

    pub fn is_new(&self) -> bool {
        self.guard.as_ref().unwrap().is_new()
    }

    fn new_metadata(&self) -> &BlobMetadata {
        self.new_metadata
            .as_ref()
            .unwrap_or_else(|| self.guard.as_ref().unwrap().blob_metadata())
    }

    fn new_metadata_mut(&mut self) -> &mut BlobMetadata {
        self.new_metadata
            .get_or_insert_with(|| self.guard.as_ref().unwrap().blob_metadata().clone())
    }

    pub fn metadata(&self) -> Option<Bytes> {
        self.new_metadata().metadata.clone()
    }

    pub fn size(&self) -> u64 {
        self.new_metadata().size
    }

    pub fn expire_at(&self) -> Option<Timestamp> {
        self.new_metadata().expire_at
    }

    pub fn set_metadata(&mut self, metadata: Option<Bytes>) {
        self.new_metadata_mut().metadata = metadata;
    }

    pub fn set_expire_at(&mut self, expire_at: Option<Timestamp>) {
        self.new_metadata_mut().expire_at = expire_at;
    }

    // TODO: Should we convert `open` to async with `spawn_blocking`?
    pub fn open(&mut self) -> Result<&mut File, Error> {
        self.ensure_file(self.truncate)?;
        Ok(self.file.as_mut().unwrap())
    }

    fn ensure_file(&mut self, truncate: bool) -> Result<(), Error> {
        if self.file.is_some() {
            return Ok(());
        }
        let is_new = self.guard.as_ref().unwrap().is_new();
        if is_new {
            // TODO: Is there an atomic `create_dir_if_not_exist`?
            if let Err(error) = fs::create_dir(self.path.parent().unwrap()) {
                if error.kind() != ErrorKind::AlreadyExists {
                    return Err(error);
                }
            }
        }
        self.file = Some(
            OpenOptions::new()
                .create_new(is_new)
                .write(true)
                .truncate(truncate)
                .open(&self.path)?,
        );
        Ok(())
    }

    // On commit error, the blob will be removed by `drop` below.
    pub fn commit(mut self) -> Result<(), Error> {
        self.new_metadata_mut();
        self.ensure_file(false)?;

        let mut new_metadata = self.new_metadata.take().unwrap();
        new_metadata.size = self.file.as_ref().unwrap().metadata()?.len();

        new_metadata.write(&self.path)?;

        // No errors after this point.

        if let Some(expire_at) = new_metadata.expire_at {
            self.expire_queue.push(expire_at, new_metadata.key.clone());
        }
        self.guard.take().unwrap().commit(new_metadata);

        self.file = None;
        Ok(())
    }
}

// TODO: I am not sure if this is a good design, but if the caller opened the writer without
// committing, I will assume an error has occurred and remove the blob.
//
// NOTE: This starts to smell like a bad design, but we only consider file-opening, not metadata
// changes.
impl Drop for WriteGuard {
    fn drop(&mut self) {
        if self.file.is_some() {
            fs::remove_file(&self.path).unwrap();
            self.guard.take().unwrap().commit_remove();
        }
    }
}

impl ExpireGuard {
    fn new(expire_queue: ExpireQueue, expire_at: Timestamp, key: Bytes) -> Self {
        Self {
            expire_queue,
            rollback: Some((expire_at, key)),
        }
    }

    fn commit(mut self) {
        self.rollback = None;
    }
}

impl Drop for ExpireGuard {
    fn drop(&mut self) {
        if let Some((expire_at, key)) = self.rollback.take() {
            self.expire_queue.push(expire_at, key);
        }
    }
}

#[cfg(test)]
mod test_harness {
    use std::io::{Read, Write};

    use super::*;

    impl ReadGuard {
        pub(super) fn read(&mut self) -> Result<Bytes, Error> {
            let mut buf = Vec::new();
            self.open()?.read_to_end(&mut buf)?;
            Ok(buf.into())
        }
    }

    impl WriteGuard {
        pub(super) fn write<T: AsRef<[u8]>>(&mut self, data: T) -> Result<(), Error> {
            self.file.as_mut().unwrap().write_all(data.as_ref())
        }
    }
}

#[cfg(test)]
mod tests {
    use std::assert_matches::assert_matches;
    use std::collections::HashMap;
    use std::fs;

    use tempfile;

    use crate::hash::KeyHash;

    use super::*;

    fn b(bytes: &'static str) -> Bytes {
        Bytes::from_static(bytes.as_bytes())
    }

    fn assert_dir<const N: usize>(dir: &Path, expect: [(&'static [u8], &'static [u8]); N]) {
        let mut actual = HashMap::new();
        let result: Result<(), Error> = try {
            for blob_dir in dir.read_dir()? {
                let blob_dir = hash::match_blob_dir(&blob_dir?)?.unwrap();
                for blob in blob_dir.read_dir()? {
                    let blob = &hash::match_blob(&blob?)?.unwrap();
                    assert_eq!(
                        actual.insert(KeyHash::from_path(blob), Bytes::from(fs::read(blob)?)),
                        None,
                    );
                }
            }
        };
        result.unwrap();
        let expect = expect
            .iter()
            .map(|(key, content)| (KeyHash::new(key), Bytes::from_static(content)))
            .collect::<HashMap<_, _>>();
        assert_eq!(actual, expect);
    }

    #[tokio::test]
    async fn open() -> Result<(), Error> {
        let tempdir = tempfile::tempdir()?;

        let blob_1 = KeyHash::new(b"foo").to_path(tempdir.path());
        let blob_2 = KeyHash::new(b"bar").to_path(tempdir.path());
        let blob_dir_1 = blob_1.parent().unwrap();
        let blob_dir_2 = blob_2.parent().unwrap();
        assert_ne!(blob_dir_1, blob_dir_2);
        let ignored = tempdir.path().join("ignored");

        let try_exists = || {
            Ok::<_, Error>((
                blob_dir_1.try_exists()?,
                blob_1.try_exists()?,
                blob_dir_2.try_exists()?,
                blob_2.try_exists()?,
                ignored.try_exists()?,
            ))
        };

        fs::create_dir(blob_dir_1)?;
        fs::write(&blob_1, b"Hello, World!")?;
        BlobMetadata::new(b("foo")).write(&blob_1)?;

        fs::create_dir(blob_dir_2)?;
        fs::write(&blob_2, b"Spam eggs")?;
        // Missing blob key.

        fs::write(&ignored, b"xyz")?;

        assert_eq!(try_exists()?, (true, true, true, true, true));

        let storage = Storage::open(tempdir.path()).await?;
        assert_eq!(storage.size(), 13);
        assert_eq!(try_exists()?, (true, true, false, false, true));

        {
            let mut guard = storage.read(b("foo")).await.unwrap();
            assert_eq!(guard.size(), 13);
            assert_eq!(guard.read()?, b("Hello, World!"));
        }

        storage.remove(b("foo")).await?;
        assert_eq!(try_exists()?, (true, false, false, false, true));

        drop(storage);
        assert_eq!(try_exists()?, (true, false, false, false, true));

        drop(Storage::open(tempdir.path()).await?);
        assert_eq!(try_exists()?, (false, false, false, false, true));

        fs::create_dir(blob_dir_2)?;
        fs::write(&blob_2, b"Spam eggs")?;
        // Write mismatched blob key.
        BlobMetadata::new(b("foo")).write(&blob_2)?;
        assert_eq!(try_exists()?, (false, false, true, true, true));

        drop(Storage::open(tempdir.path()).await?);
        assert_eq!(try_exists()?, (false, false, false, false, true));

        Ok(())
    }

    #[tokio::test]
    async fn evict() -> Result<(), Error> {
        let tempdir = tempfile::tempdir()?;
        let storage = Storage::open(tempdir.path()).await?;
        assert_eq!(storage.size(), 0);
        assert_dir(tempdir.path(), []);

        assert_eq!(storage.evict(0).await?, 0);

        {
            let mut guard = storage.write(b("foo"), true).await?;
            guard.open()?;
            guard.write(b"Hello, World!")?;
            guard.commit()?;
        }
        assert_eq!(storage.size(), 13);
        {
            let mut guard = storage.write(b("bar"), true).await?;
            guard.open()?;
            guard.write(b"spam eggs")?;
            guard.commit()?;
        }
        assert_eq!(storage.size(), 22);
        assert_dir(
            tempdir.path(),
            [(b"foo", b"Hello, World!"), (b"bar", b"spam eggs")],
        );

        assert_eq!(storage.evict(9).await?, 9);
        assert_dir(tempdir.path(), [(b"bar", b"spam eggs")]);
        assert_matches!(storage.read(b("foo")).await, None);

        let guard = storage.read(b("bar")).await.unwrap();
        assert_eq!(storage.evict(0).await?, 9);
        assert_dir(tempdir.path(), [(b"bar", b"spam eggs")]);

        drop(guard);
        assert_eq!(storage.evict(0).await?, 0);
        assert_dir(tempdir.path(), []);

        Ok(())
    }

    #[tokio::test]
    async fn expire() -> Result<(), Error> {
        let t1 = Timestamp::from_timestamp_secs(1).unwrap();
        let t2 = Timestamp::from_timestamp_secs(2).unwrap();
        let t3 = Timestamp::from_timestamp_secs(3).unwrap();

        let tempdir = tempfile::tempdir()?;
        let storage = Storage::open(tempdir.path()).await?;
        assert_eq!(storage.size(), 0);
        assert_dir(tempdir.path(), []);

        for key in [b("k1"), b("k2"), b("k3")] {
            let mut guard = storage.write(key, true).await?;
            guard.open()?;
            guard.write(b"x")?;
            guard.commit()?;
        }
        assert_dir(
            tempdir.path(),
            [(b"k1", b"x"), (b"k2", b"x"), (b"k3", b"x")],
        );
        assert_eq!(storage.next_expire_at(), None);

        storage.expire(t2).await?;
        assert_dir(
            tempdir.path(),
            [(b"k1", b"x"), (b"k2", b"x"), (b"k3", b"x")],
        );

        for (key, expire_at) in [(b("k1"), t1), (b("k2"), t2), (b("k3"), t3)] {
            let mut guard = storage.write(key, true).await?;
            guard.set_expire_at(Some(expire_at));
            guard.commit()?;
        }
        assert_dir(
            tempdir.path(),
            [(b"k1", b"x"), (b"k2", b"x"), (b"k3", b"x")],
        );
        assert_eq!(storage.next_expire_at(), Some(t1));

        storage.expire(t2).await?;
        assert_dir(tempdir.path(), [(b"k3", b"x")]);
        assert_eq!(storage.next_expire_at(), Some(t3));

        Ok(())
    }

    #[tokio::test]
    async fn read() -> Result<(), Error> {
        let tempdir = tempfile::tempdir()?;
        let storage = Storage::open(tempdir.path()).await?;
        assert_eq!(storage.size(), 0);
        assert_dir(tempdir.path(), []);

        assert_matches!(storage.read(b("foo")).await, None);

        {
            let mut guard = storage.write(b("foo"), true).await?;
            guard.set_metadata(Some(b("Spam eggs")));
            guard.open()?;
            guard.write(b"Hello, World!")?;
            guard.commit()?;
        }
        assert_eq!(storage.size(), 13);
        assert_dir(tempdir.path(), [(b"foo", b"Hello, World!")]);

        {
            let mut guards = [
                storage.read(b("foo")).await.unwrap(),
                storage.read(b("foo")).await.unwrap(),
            ];
            for guard in &mut guards {
                assert_eq!(guard.size(), 13);
                assert_eq!(guard.metadata(), Some(b("Spam eggs")));
                assert_eq!(guard.read()?, b("Hello, World!"));
            }
        }

        {
            let mut guard = storage.write(b("foo"), false).await?;
            guard.set_metadata(None);
            guard.commit()?;
        }
        assert_eq!(storage.size(), 13);
        assert_dir(tempdir.path(), [(b"foo", b"Hello, World!")]);

        {
            let mut guards = [
                storage.read(b("foo")).await.unwrap(),
                storage.read(b("foo")).await.unwrap(),
            ];
            for guard in &mut guards {
                assert_eq!(guard.size(), 13);
                assert_eq!(guard.metadata(), None);
                assert_eq!(guard.read()?, b("Hello, World!"));
            }
        }

        Ok(())
    }

    #[tokio::test]
    async fn write() -> Result<(), Error> {
        let tempdir = tempfile::tempdir()?;
        let storage = Storage::open(tempdir.path()).await?;
        assert_eq!(storage.size(), 0);
        assert_dir(tempdir.path(), []);

        {
            let mut guard = storage.write(b("foo"), true).await?;
            guard.set_metadata(Some(b("Spam eggs")));
            guard.open()?;
            guard.write(b"Hello, World!")?;
            guard.commit()?;
        }
        assert_eq!(storage.size(), 13);
        assert_dir(tempdir.path(), [(b"foo", b"Hello, World!")]);
        {
            let mut guard = storage.read(b("foo")).await.unwrap();
            assert_eq!(guard.metadata(), Some(b("Spam eggs")));
            assert_eq!(guard.read()?, b("Hello, World!"));
        }

        // No open nor set blob metadata.
        drop(storage.write(b("foo"), false).await?);
        assert_eq!(storage.size(), 13);
        assert_dir(tempdir.path(), [(b"foo", b"Hello, World!")]);
        {
            let mut guard = storage.read(b("foo")).await.unwrap();
            assert_eq!(guard.metadata(), Some(b("Spam eggs")));
            assert_eq!(guard.read()?, b("Hello, World!"));
        }

        // Set blob metadata only.
        {
            let mut guard = storage.write(b("foo"), false).await?;
            guard.set_metadata(Some(b("Something else")));
        }
        assert_eq!(storage.size(), 13);
        assert_dir(tempdir.path(), [(b"foo", b"Hello, World!")]);
        {
            let mut guard = storage.read(b("foo")).await.unwrap();
            assert_eq!(guard.metadata(), Some(b("Spam eggs")));
            assert_eq!(guard.read()?, b("Hello, World!"));
        }

        // No write.
        {
            let mut guard = storage.write(b("foo"), false).await?;
            guard.set_metadata(Some(b("Something else")));
            guard.commit()?;
        }
        assert_eq!(storage.size(), 13);
        assert_dir(tempdir.path(), [(b"foo", b"Hello, World!")]);
        {
            let mut guard = storage.read(b("foo")).await.unwrap();
            assert_eq!(guard.metadata(), Some(b("Something else")));
            assert_eq!(guard.read()?, b("Hello, World!"));
        }

        // Truncate.
        {
            let mut guard = storage.write(b("foo"), true).await?;
            guard.open()?;
            guard.commit()?;
        }
        assert_eq!(storage.size(), 0);
        assert_dir(tempdir.path(), [(b"foo", b"")]);
        {
            let mut guard = storage.read(b("foo")).await.unwrap();
            assert_eq!(guard.metadata(), Some(b("Something else")));
            assert_eq!(guard.read()?, b(""));
        }

        // No commit.
        {
            let mut guard = storage.write(b("foo"), true).await?;
            guard.open()?;
        }
        assert_eq!(storage.size(), 0);
        assert_dir(tempdir.path(), []);
        assert_matches!(storage.read(b("foo")).await, None);

        Ok(())
    }

    #[tokio::test]
    async fn try_write() -> Result<(), Error> {
        let tempdir = tempfile::tempdir()?;
        let storage = Storage::open(tempdir.path()).await?;
        assert_eq!(storage.size(), 0);
        assert_dir(tempdir.path(), []);

        {
            let mut guard = storage.try_write(b("foo"), true).unwrap();
            guard.open()?;
            guard.write(b"Hello, World!")?;

            assert_matches!(storage.try_write(b("foo"), true), None);

            guard.commit()?;
        }
        assert_eq!(storage.size(), 13);
        assert_dir(tempdir.path(), [(b"foo", b"Hello, World!")]);

        {
            let _guard = storage.read(b("foo")).await.unwrap();
            assert_matches!(storage.try_write(b("foo"), true), None);
        }
        assert_eq!(storage.size(), 13);
        assert_dir(tempdir.path(), [(b"foo", b"Hello, World!")]);

        Ok(())
    }

    #[tokio::test]
    async fn remove() -> Result<(), Error> {
        let tempdir = tempfile::tempdir()?;
        let storage = Storage::open(tempdir.path()).await?;
        assert_eq!(storage.size(), 0);
        assert_dir(tempdir.path(), []);

        assert_matches!(storage.remove(b("foo")).await?, None);

        {
            let mut guard = storage.write(b("foo"), true).await?;
            guard.open()?;
            guard.write(b"x")?;
            guard.commit()?;
        }
        assert_eq!(storage.size(), 1);
        {
            let mut guard = storage.write(b("bar"), true).await?;
            guard.open()?;
            guard.write(b"yz")?;
            guard.commit()?;
        }
        assert_eq!(storage.size(), 3);
        assert_dir(tempdir.path(), [(b"foo", b"x"), (b"bar", b"yz")]);

        assert_matches!(storage.remove(b("foo")).await?, Some(_));
        assert_eq!(storage.size(), 2);
        assert_dir(tempdir.path(), [(b"bar", b"yz")]);
        assert_matches!(storage.read(b("foo")).await, None);

        Ok(())
    }

    #[tokio::test]
    async fn try_remove_front() -> Result<(), Error> {
        let tempdir = tempfile::tempdir()?;
        let storage = Storage::open(tempdir.path()).await?;
        assert_eq!(storage.size(), 0);
        assert_dir(tempdir.path(), []);

        assert_matches!(storage.try_remove_front()?, None);

        {
            let mut guard = storage.write(b("foo"), true).await?;
            guard.open()?;
            guard.write(b"x")?;
            guard.commit()?;
        }
        assert_eq!(storage.size(), 1);
        {
            let mut guard = storage.write(b("bar"), true).await?;
            guard.open()?;
            guard.write(b"yz")?;
            guard.commit()?;
        }
        assert_eq!(storage.size(), 3);
        assert_dir(tempdir.path(), [(b"foo", b"x"), (b"bar", b"yz")]);

        let guard = storage.read(b("foo")).await.unwrap();

        assert_matches!(storage.try_remove_front()?, Some(_));
        assert_eq!(storage.size(), 1);
        assert_dir(tempdir.path(), [(b"foo", b"x")]);
        assert_matches!(storage.read(b("bar")).await, None);

        assert_matches!(storage.try_remove_front()?, None);
        assert_eq!(storage.size(), 1);
        assert_dir(tempdir.path(), [(b"foo", b"x")]);

        drop(guard);

        assert_matches!(storage.try_remove_front()?, Some(_));
        assert_eq!(storage.size(), 0);
        assert_dir(tempdir.path(), []);
        assert_matches!(storage.read(b("foo")).await, None);

        Ok(())
    }
}
