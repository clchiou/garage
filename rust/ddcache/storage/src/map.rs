use std::assert_matches::assert_matches;
use std::cmp::Reverse;
use std::io::Error;
use std::path::Path;
use std::sync::{
    atomic::{AtomicU64, Ordering},
    Arc, Mutex,
};

use bytes::Bytes;
use tokio::sync::{OwnedRwLockReadGuard, OwnedRwLockWriteGuard, RwLock};
use tokio::task;

use g1_base::collections::HashOrderedMap;
use g1_base::sync::MutexExt;

use crate::blob::BlobMetadata;
use crate::hash::KeyHash;
use crate::RawExpireQueue;

//
// Implementer's Notes: To ensure cancel safety, `BlobMap` should return guard types that maintain
// the map's invariants, instead of delegating this responsibility to the caller.
//

#[derive(Clone, Debug)]
pub(crate) struct BlobMap(Arc<Inner>);

#[derive(Debug)]
struct Inner {
    map: Mutex<HashOrderedMap<KeyHash, Entry>>,
    size: AtomicU64,
}

#[derive(Debug)]
pub(crate) struct BlobMapBuilder {
    map: HashOrderedMap<KeyHash, Entry>,
    size: u64,
    expire_queue: RawExpireQueue,
}

#[derive(Debug)]
pub(crate) struct ReadGuard {
    guard: OwnedRwLockReadGuard<State>,
}

#[derive(Debug)]
pub(crate) struct WriteGuard {
    guard: Option<OwnedRwLockWriteGuard<State>>,
    inner: Arc<Inner>,
    hash: KeyHash,
}

#[derive(Debug)]
pub(crate) struct RemoveGuard {
    guard: OwnedRwLockWriteGuard<State>,
    inner: Arc<Inner>,
    hash: KeyHash,
}

#[derive(Debug)]
struct Entry {
    // Duplicate the key here so that we can compare it without locking the state.
    key: Bytes,
    state: Arc<RwLock<State>>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum State {
    New(BlobMetadata),
    Present(BlobMetadata),
    Removing,
}

impl BlobMapBuilder {
    pub(crate) fn new() -> Self {
        Self {
            map: HashOrderedMap::new(),
            size: 0,
            expire_queue: RawExpireQueue::new(),
        }
    }

    pub(crate) fn insert(&mut self, blob: &Path) -> Result<(), Error> {
        let blob_metadata = BlobMetadata::read(blob)?;
        let hash = KeyHash::from_path(blob);
        if KeyHash::new(&blob_metadata.key) != hash {
            return Err(Error::other(format!(
                "expect hash(key) == {}: {:?}",
                blob.display(),
                blob_metadata,
            )));
        }

        if let Some(expire_at) = blob_metadata.expire_at {
            self.expire_queue
                .push(Reverse((expire_at, blob_metadata.key.clone())));
        }

        self.size += blob_metadata.size;
        assert!(self.map.insert(hash, blob_metadata.into()).is_none());

        Ok(())
    }

    pub(crate) fn build(self) -> (BlobMap, RawExpireQueue) {
        (BlobMap::new(self.map, self.size), self.expire_queue)
    }
}

impl BlobMap {
    fn new(map: HashOrderedMap<KeyHash, Entry>, size: u64) -> Self {
        Self(Arc::new(Inner {
            map: Mutex::new(map),
            size: AtomicU64::new(size),
        }))
    }

    pub(crate) fn keys(&self) -> Vec<Bytes> {
        self.0
            .map
            .must_lock()
            .values()
            .map(|entry| entry.key.clone())
            .collect()
    }

    pub(crate) fn size(&self) -> u64 {
        self.0.size.load(Ordering::SeqCst)
    }

    fn get(&self, key: &Bytes, hash: KeyHash) -> Option<Arc<RwLock<State>>> {
        self.0
            .map
            .must_lock()
            .get(&hash)
            .filter(|entry| entry.key == key)
            .map(|entry| entry.state.clone())
    }

    fn get_back(&self, key: &Bytes, hash: KeyHash) -> Option<Arc<RwLock<State>>> {
        self.0
            .map
            .must_lock()
            .get_mut_back(&hash)
            .filter(|entry| entry.key == key)
            .map(|entry| entry.state.clone())
    }

    //
    // Implementer's Notes: We move the entry to the back even when a hash collision occurs.  While
    // not perfect, this should not be an issue in practice.
    //

    pub(crate) async fn read(&self, key: Bytes) -> Option<(KeyHash, ReadGuard)> {
        self.do_read(key, |k, h| self.get_back(k, h)).await
    }

    pub(crate) async fn peek(&self, key: Bytes) -> Option<(KeyHash, ReadGuard)> {
        self.do_read(key, |k, h| self.get(k, h)).await
    }

    async fn do_read<F>(&self, key: Bytes, get_entry: F) -> Option<(KeyHash, ReadGuard)>
    where
        F: FnOnce(&Bytes, KeyHash) -> Option<Arc<RwLock<State>>>,
    {
        let hash = KeyHash::new(&key);
        let guard = get_entry(&key, hash)?.read_owned().await;
        guard
            .ensure_present()
            .then(|| (hash, ReadGuard::new(guard)))
    }

    pub(crate) async fn write(&self, key: Bytes) -> Result<(KeyHash, WriteGuard), Bytes> {
        const NUM_TRIES: usize = 8;
        let hash = KeyHash::new(&key);
        for _ in 0..NUM_TRIES {
            let state = match self.write_lock(key.clone(), hash)? {
                Ok(guard) => return Ok(guard),
                Err(state) => state,
            };
            let guard = state.write_owned().await;
            match *guard {
                State::New(_) => std::unreachable!(),
                State::Present(_) => return Ok(self.new_write_guard(hash, guard)),
                State::Removing => task::yield_now().await,
            }
        }
        std::panic!("map is stuck in removing entry: {:?} {:?}", key, hash);
    }

    pub(crate) fn write_new(&self, key: Bytes) -> Option<(KeyHash, WriteGuard)> {
        let hash = KeyHash::new(&key);
        let mut map = self.0.map.must_lock();
        if map.contains_key(&hash) {
            return None;
        }
        // Cancel Safety: For a newly inserted entry, we must protect it with a `WriteGuard`
        // immediately.
        let entry = Entry::new(key);
        let guard = entry.state.clone().try_write_owned().unwrap();
        assert!(map.insert(hash, entry).is_none());
        Some(self.new_write_guard(hash, guard))
    }

    pub(crate) fn try_write(&self, key: Bytes) -> Option<(KeyHash, WriteGuard)> {
        let hash = KeyHash::new(&key);
        match self.write_lock(key, hash).ok()? {
            Ok(guard) => Some(guard),
            Err(state) => {
                let guard = state.try_write_owned().ok()?;
                guard
                    .ensure_present()
                    .then(|| self.new_write_guard(hash, guard))
            }
        }
    }

    #[allow(clippy::type_complexity)]
    fn write_lock(
        &self,
        key: Bytes,
        hash: KeyHash,
    ) -> Result<Result<(KeyHash, WriteGuard), Arc<RwLock<State>>>, Bytes> {
        let mut map = self.0.map.must_lock();
        match map.get_mut_back(&hash) {
            Some(entry) => {
                if entry.key == key {
                    Ok(Err(entry.state.clone()))
                } else {
                    Err(entry.key.clone())
                }
            }
            None => {
                // Cancel Safety: For a newly inserted entry, we must protect it with a
                // `WriteGuard` immediately.
                let entry = Entry::new(key);
                let guard = entry.state.clone().try_write_owned().unwrap();
                assert!(map.insert(hash, entry).is_none());
                Ok(Ok(self.new_write_guard(hash, guard)))
            }
        }
    }

    fn new_write_guard(
        &self,
        hash: KeyHash,
        guard: OwnedRwLockWriteGuard<State>,
    ) -> (KeyHash, WriteGuard) {
        (hash, WriteGuard::new(guard, self.0.clone(), hash))
    }

    pub(crate) async fn remove(&self, key: Bytes) -> Option<(KeyHash, RemoveGuard)> {
        let hash = KeyHash::new(&key);
        let guard = self.get(&key, hash)?.write_owned().await;
        guard
            .ensure_present()
            .then(|| self.new_remove_guard(hash, guard))
    }

    pub(crate) fn try_remove_front(&self) -> Option<(KeyHash, RemoveGuard)> {
        self.0.map.must_lock().iter().find_map(|(hash, entry)| {
            let guard = entry.state.clone().try_write_owned().ok()?;
            guard
                .ensure_present()
                .then(|| self.new_remove_guard(*hash, guard))
        })
    }

    fn new_remove_guard(
        &self,
        hash: KeyHash,
        guard: OwnedRwLockWriteGuard<State>,
    ) -> (KeyHash, RemoveGuard) {
        (hash, RemoveGuard::new(guard, self.0.clone(), hash))
    }
}

impl ReadGuard {
    fn new(guard: OwnedRwLockReadGuard<State>) -> Self {
        assert_matches!(*guard, State::Present(_));
        Self { guard }
    }

    pub(crate) fn blob_metadata(&self) -> &BlobMetadata {
        self.guard.blob_metadata()
    }
}

impl WriteGuard {
    fn new(guard: OwnedRwLockWriteGuard<State>, inner: Arc<Inner>, hash: KeyHash) -> Self {
        assert_matches!(*guard, State::New(_) | State::Present(_));
        Self {
            guard: Some(guard),
            inner,
            hash,
        }
    }

    fn state(&self) -> &State {
        self.guard.as_ref().unwrap()
    }

    pub(crate) fn is_new(&self) -> bool {
        self.state().is_new()
    }

    pub(crate) fn blob_metadata(&self) -> &BlobMetadata {
        self.state().blob_metadata()
    }

    pub(crate) fn commit(mut self, new_metadata: BlobMetadata) {
        let mut guard = self.guard.take().unwrap();
        let old_metadata = guard.blob_metadata();

        // You cannot change the key.
        assert_eq!(old_metadata.key, new_metadata.key);

        let new_size = new_metadata.size;
        let old_size = old_metadata.size;
        if new_size >= old_size {
            self.inner
                .size
                .fetch_add(new_size - old_size, Ordering::SeqCst);
        } else {
            self.inner
                .size
                .fetch_sub(old_size - new_size, Ordering::SeqCst);
        }

        *guard = State::Present(new_metadata);
    }
}

macro_rules! map_remove {
    ($self:ident, $guard:ident) => {{
        // Change the map entry state to the sentinel value.
        *$guard = State::Removing;
        drop($guard);
        // Remove the entry after the guard is dropped.
        assert!($self.inner.map.must_lock().remove(&$self.hash).is_some());
    }};
}

impl WriteGuard {
    pub(crate) fn commit_remove(mut self) {
        let mut guard = self.guard.take().unwrap();
        self.inner
            .size
            .fetch_sub(guard.blob_metadata().size, Ordering::SeqCst);
        map_remove!(self, guard);
    }
}

impl Drop for WriteGuard {
    fn drop(&mut self) {
        if let Some(mut guard) = self.guard.take() {
            if guard.is_new() {
                map_remove!(self, guard);
            }
        }
    }
}

impl RemoveGuard {
    fn new(guard: OwnedRwLockWriteGuard<State>, inner: Arc<Inner>, hash: KeyHash) -> Self {
        assert_matches!(*guard, State::Present(_));
        Self { guard, inner, hash }
    }

    pub(crate) fn blob_metadata(&self) -> &BlobMetadata {
        self.guard.blob_metadata()
    }

    pub(crate) fn commit(self) {
        self.inner
            .size
            .fetch_sub(self.guard.blob_metadata().size, Ordering::SeqCst);
        let mut guard = self.guard;
        map_remove!(self, guard);
    }
}

impl From<BlobMetadata> for Entry {
    fn from(blob_metadata: BlobMetadata) -> Self {
        Self::new_impl(blob_metadata.key.clone(), State::Present(blob_metadata))
    }
}

impl Entry {
    fn new(key: Bytes) -> Self {
        Self::new_impl(key.clone(), State::New(BlobMetadata::new(key)))
    }

    fn new_impl(key: Bytes, state: State) -> Self {
        Self {
            key,
            state: Arc::new(RwLock::new(state)),
        }
    }
}

impl State {
    fn is_new(&self) -> bool {
        matches!(self, State::New(_))
    }

    fn ensure_present(&self) -> bool {
        // `State::New` is always locked by a write lock, making it "invisible" to other locks.
        match self {
            State::New(_) => std::panic!("expect State::Present of State::Removing"),
            State::Present(_) => true,
            State::Removing => false,
        }
    }

    fn blob_metadata(&self) -> &BlobMetadata {
        match self {
            Self::New(blob_metadata) | Self::Present(blob_metadata) => blob_metadata,
            Self::Removing => std::panic!("expect State::New or State::Present"),
        }
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl BlobMap {
        pub(super) fn new_mock<const N: usize>(
            entries: [(&'static [u8], State); N],
            size: u64,
        ) -> Self {
            let map = entries
                .into_iter()
                .map(|(key, state)| (KeyHash::new(key), Entry::new_mock(key, state)))
                .collect();
            Self::new(map, size)
        }

        pub(super) fn entries(&self) -> Vec<(KeyHash, Bytes, State)> {
            self.0
                .map
                .must_lock()
                .iter()
                .map(|(hash, entry)| {
                    (
                        *hash,
                        entry.key.clone(),
                        unsafe { &mut *(Arc::as_ptr(&entry.state) as *mut RwLock<State>) }
                            .get_mut()
                            .clone(),
                    )
                })
                .collect()
        }

        // This is for faking hash collisions.
        pub(super) fn insert_mock(&self, hash: KeyHash, key: &'static [u8], state: State) {
            self.0
                .map
                .must_lock()
                .insert(hash, Entry::new_mock(key, state));
        }

        pub(super) fn assert_eq<const N: usize>(
            &self,
            entries: [(&'static [u8], State); N],
            size: u64,
        ) {
            let expect: Vec<_> = entries
                .into_iter()
                .map(|(key, state)| (KeyHash::new(key), Bytes::from_static(key), state))
                .collect();
            assert_eq!(self.entries(), expect);
            assert_eq!(self.size(), size);
        }

        // Call this when fake hashes are present.
        pub(super) fn assert_eq_with_hash<const N: usize>(
            &self,
            entries: [(KeyHash, &'static [u8], State); N],
            size: u64,
        ) {
            let expect: Vec<_> = entries
                .into_iter()
                .map(|(hash, key, state)| (hash, Bytes::from_static(key), state))
                .collect();
            assert_eq!(self.entries(), expect);
            assert_eq!(self.size(), size);
        }
    }

    impl Entry {
        pub(super) fn new_mock(key: &'static [u8], state: State) -> Self {
            Self::new_impl(key.into(), state)
        }
    }

    impl State {
        pub(super) const fn new_mock(size: u64, key: &'static [u8]) -> Self {
            let blob_metadata = BlobMetadata::new_mock(key, None, size);
            if size == 0 {
                Self::New(blob_metadata)
            } else {
                Self::Present(blob_metadata)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const fn e(key: &'static [u8], size: u64) -> (&'static [u8], State) {
        (key, State::new_mock(size, key))
    }

    const N: (&'static [u8], State) = e(b"new", 0);
    const P: (&'static [u8], State) = e(b"present", 10);
    const R: (&'static [u8], State) = (b"removing", State::Removing);

    fn b(bytes: &'static str) -> Bytes {
        Bytes::from_static(bytes.as_bytes())
    }

    fn h(bytes: &'static str) -> KeyHash {
        KeyHash::new(bytes.as_bytes())
    }

    #[tokio::test]
    async fn read() {
        let map = BlobMap::new_mock([N, P, R], 20);
        map.assert_eq([N, P, R], 20);

        assert_matches!(
            map.read(b("present")).await,
            Some((hash, guard)) if hash == h("present") && guard.blob_metadata().size == 10,
        );
        map.assert_eq([N, R, P], 20);

        assert_matches!(map.read(b("removing")).await, None);
        map.assert_eq([N, P, R], 20);

        assert_matches!(map.read(b("no-such-key")).await, None);
        map.assert_eq([N, P, R], 20);
    }

    #[tokio::test]
    #[should_panic(expected = "expect State::Present of State::Removing")]
    async fn read_panic() {
        let map = BlobMap::new_mock([N, P, R], 20);
        map.assert_eq([N, P, R], 20);

        let _ = map.read(b("new")).await;
    }

    #[tokio::test]
    async fn peek() {
        let map = BlobMap::new_mock([e(b"k1", 1), e(b"k2", 2), e(b"k3", 3)], 6);
        map.assert_eq([e(b"k1", 1), e(b"k2", 2), e(b"k3", 3)], 6);
        for key in ["k1", "k2", "k3"] {
            assert_matches!(map.peek(b(key)).await, Some((hash, _)) if hash == h(key));
            map.assert_eq([e(b"k1", 1), e(b"k2", 2), e(b"k3", 3)], 6);
        }
    }

    #[tokio::test]
    async fn write() {
        let map = BlobMap::new_mock([P, R], 20);
        map.assert_eq([P, R], 20);

        {
            let entry = map.write(b("present")).await;
            assert_matches!(
                entry,
                Ok((hash, ref guard)) if hash == h("present") && !guard.is_new(),
            );
            map.assert_eq([R, P], 20);

            drop(entry);
            map.assert_eq([R, P], 20);
        }

        {
            let entry = map.write(b("foo")).await;
            assert_matches!(entry, Ok((hash, ref guard)) if hash == h("foo") && guard.is_new());
            map.assert_eq([R, P, e(b"foo", 0)], 20);

            drop(entry);
            map.assert_eq([R, P], 20);
        }

        {
            let entry = map.write(b("foo")).await;
            assert_matches!(entry, Ok((hash, ref guard)) if hash == h("foo") && guard.is_new());
            map.assert_eq([R, P, e(b"foo", 0)], 20);

            entry.unwrap().1.commit_remove();
            map.assert_eq([R, P], 20);
        }

        {
            let entry = map.write(b("foo")).await;
            assert_matches!(entry, Ok((hash, ref guard)) if hash == h("foo") && guard.is_new());
            map.assert_eq([R, P, e(b"foo", 0)], 20);

            let blob_metadata = BlobMetadata::new_mock(b"foo", None, 100);
            entry.unwrap().1.commit(blob_metadata);
            map.assert_eq([R, P, e(b"foo", 100)], 120);
        }

        {
            let entry = map.write(b("foo")).await;
            assert_matches!(entry, Ok((hash, ref guard)) if hash == h("foo") && !guard.is_new());
            map.assert_eq([R, P, e(b"foo", 100)], 120);

            entry.unwrap().1.commit_remove();
            map.assert_eq([R, P], 20);
        }
    }

    #[tokio::test]
    #[should_panic(expected = "map is stuck in removing entry: ")]
    async fn write_panic() {
        let map = BlobMap::new_mock([P, R], 20);
        map.assert_eq([P, R], 20);

        let _ = map.write(b("removing")).await;
    }

    #[test]
    fn write_new() {
        let map = BlobMap::new_mock([P, R], 20);
        map.assert_eq([P, R], 20);

        assert_matches!(map.write_new(b("present")), None);
        map.assert_eq([P, R], 20);

        {
            let entry = map.write_new(b("foo"));
            assert_matches!(entry, Some((hash, ref guard)) if hash == h("foo") && guard.is_new());
            map.assert_eq([P, R, e(b"foo", 0)], 20);

            assert_matches!(map.write_new(b("foo")), None);

            drop(entry);
            map.assert_eq([P, R], 20);
        }
    }

    #[test]
    fn try_write() {
        let map = BlobMap::new_mock([P, R], 20);
        map.assert_eq([P, R], 20);

        {
            let entry = map.try_write(b("present"));
            assert_matches!(
                entry,
                Some((hash, ref guard)) if hash == h("present") && !guard.is_new(),
            );
            map.assert_eq([R, P], 20);

            drop(entry);
            map.assert_eq([R, P], 20);
        }

        {
            let entry = map.try_write(b("foo"));
            assert_matches!(entry, Some((hash, ref guard)) if hash == h("foo") && guard.is_new());
            map.assert_eq([R, P, e(b"foo", 0)], 20);

            assert_matches!(map.try_write(b("foo")), None);

            drop(entry);
            map.assert_eq([R, P], 20);
        }

        assert_matches!(map.try_write(b("removing")), None);
        map.assert_eq([P, R], 20);
    }

    #[tokio::test]
    async fn remove() {
        let map = BlobMap::new_mock([N, P, R], 20);
        map.assert_eq([N, P, R], 20);

        assert_matches!(map.remove(b("removing")).await, None);
        map.assert_eq([N, P, R], 20);

        assert_matches!(map.remove(b("no-such-key")).await, None);
        map.assert_eq([N, P, R], 20);

        {
            let entry = map.remove(b("present")).await;
            assert_matches!(entry, Some((hash, _)) if hash == h("present"));
            map.assert_eq([N, P, R], 20);

            drop(entry);
            map.assert_eq([N, P, R], 20);
        }

        {
            let entry = map.remove(b("present")).await;
            assert_matches!(entry, Some((hash, _)) if hash == h("present"));
            map.assert_eq([N, P, R], 20);

            entry.unwrap().1.commit();
            map.assert_eq([N, R], 10);
        }
    }

    #[tokio::test]
    #[should_panic(expected = "expect State::Present of State::Removing")]
    async fn remove_panic() {
        let map = BlobMap::new_mock([N, P, R], 20);
        map.assert_eq([N, P, R], 20);

        let _ = map.remove(b("new")).await;
    }

    #[test]
    fn try_remove_front() {
        {
            let entries = [e(b"foo", 1), R, e(b"bar", 2)];
            let map = BlobMap::new_mock(entries.clone(), 20);
            map.assert_eq(entries.clone(), 20);

            let e0 = map.try_remove_front();
            assert_matches!(e0, Some((hash, _)) if hash == h("foo"));
            map.assert_eq(entries.clone(), 20);

            let e1 = map.try_remove_front();
            assert_matches!(e1, Some((hash, _)) if hash == h("bar"));
            map.assert_eq(entries.clone(), 20);

            assert_matches!(map.try_remove_front(), None);
            map.assert_eq(entries.clone(), 20);
        }

        let mut entries = [P, R];
        for _ in 0..entries.len() * 3 {
            let map = BlobMap::new_mock(entries.clone(), 20);
            map.assert_eq(entries.clone(), 20);

            assert_matches!(map.try_remove_front(), Some((hash, _)) if hash == h("present"));
            map.assert_eq(entries.clone(), 20);

            entries.rotate_right(1);
        }

        let map = BlobMap::new_mock([R], 20);
        map.assert_eq([R], 20);
        assert_matches!(map.try_remove_front(), None);
        map.assert_eq([R], 20);

        let map = BlobMap::new_mock([], 20);
        map.assert_eq([], 20);
        assert_matches!(map.try_remove_front(), None);
        map.assert_eq([], 20);
    }

    #[test]
    #[should_panic(expected = "expect State::Present of State::Removing")]
    fn try_remove_front_panic() {
        let map = BlobMap::new_mock([N, P, R], 20);
        map.assert_eq([N, P, R], 20);

        let _ = map.try_remove_front();
    }

    #[tokio::test]
    async fn collision() {
        const STATE: State = State::new_mock(10, b"bar");
        let map = BlobMap::new_mock([], 20);
        map.insert_mock(h("foo"), b"bar", STATE);
        map.assert_eq_with_hash([(h("foo"), b"bar", STATE)], 20);

        assert_matches!(map.read(b("foo")).await, None);
        map.assert_eq_with_hash([(h("foo"), b"bar", STATE)], 20);

        assert_matches!(map.write(b("foo")).await, Err(collision) if collision == b("bar"));
        map.assert_eq_with_hash([(h("foo"), b"bar", STATE)], 20);

        assert_matches!(map.try_write(b("foo")), None);
        map.assert_eq_with_hash([(h("foo"), b"bar", STATE)], 20);

        assert_matches!(map.remove(b("foo")).await, None);
        map.assert_eq_with_hash([(h("foo"), b"bar", STATE)], 20);
    }
}
