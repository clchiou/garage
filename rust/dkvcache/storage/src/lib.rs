#![feature(type_alias_impl_trait)]
#![cfg_attr(test, feature(iterator_try_collect))]

mod scan;

use std::mem;
use std::ops::Deref;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use bytes::Bytes;
use const_format::formatcp;
use rusqlite::types::ValueRef;
use rusqlite::{Connection, OptionalExtension, Row};
use scopeguard::{Always, ScopeGuard};

use g1_base::sync::MutexExt;

use crate::scan::Scanner;

g1_param::define!(connection_pool_size: usize = 16);

pub use rusqlite::Error;

#[derive(Clone, Debug)]
pub struct Storage(Arc<StorageImpl>);

#[derive(Debug)]
struct StorageImpl {
    path: PathBuf,
    pool: Mutex<Vec<Connection>>,
    connection_pool_size: usize,
    len_cache: Mutex<usize>,
    next_expire_at_cache: Mutex<Option<Timestamp>>,
    // Buffer recency updates for `get` to prevent it from opening a transaction.
    recency_buffer: Mutex<Vec<(RowId, RawTimestamp)>>,
}

// We do not access `Connection` and its derivatives concurrently from multiple threads; therefore,
// implementing `Sync` for `StorageImpl` is safe.
unsafe impl Sync for StorageImpl {}

type ConnGuard<'a> = ScopeGuard<Connection, impl FnOnce(Connection) + 'a, Always>;

type RowId = i64;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Entry {
    pub value: Bytes,
    pub expire_at: Option<Timestamp>,
}

pub use g1_chrono::{Timestamp, TimestampExt};

// We manually encode `Timestamp` (an alias for `DateTime<Utc>`) as `i64` because
// `rusqlite::types::ToSql` encodes `DateTime<Utc>` as a string, which is quite inefficient.
type RawTimestamp = i64;

const DKVCACHE: &str = "dkvcache";

// Column names.
const ROWID: &str = "rowid";
const KEY: &str = "key";
const VALUE: &str = "value";
const EXPIRE_AT: &str = "expire_at";
const RECENCY: &str = "recency";

impl Storage {
    pub fn open<P>(path: P) -> Result<Self, Error>
    where
        P: AsRef<Path>,
    {
        let this = Self(Arc::new(StorageImpl::new(path)));
        this.0.init()?;
        Ok(this)
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub fn len(&self) -> usize {
        *self.0.len_cache.must_lock()
    }

    pub fn scan(&self, most_recent: bool) -> impl Iterator<Item = Result<Bytes, Error>> {
        Scanner::new(self.clone(), most_recent).flatten()
    }

    pub fn evict(&self, target_len: usize) -> Result<usize, Error> {
        self.0.transact(move |conn| {
            let n = StorageImpl::query_len(conn)?.saturating_sub(target_len);
            if n > 0 {
                conn.prepare_cached(formatcp!(
                    // Work around the [issue] that `rusqlite` does not enable
                    // `SQLITE_ENABLE_UPDATE_DELETE_LIMIT`.
                    // [issue]: https://github.com/rusqlite/rusqlite/issues/1111
                    "WITH target (id) AS
                        (SELECT {ROWID} FROM {DKVCACHE} ORDER BY {RECENCY} ASC LIMIT ?1)
                    DELETE FROM {DKVCACHE} WHERE {ROWID} IN target"
                ))?
                .execute([n])?;
            }
            StorageImpl::query_len(conn)
        })
    }

    pub fn next_expire_at(&self) -> Option<Timestamp> {
        *self.0.next_expire_at_cache.must_lock()
    }

    pub fn expire(&self, now: Timestamp) -> Result<(), Error> {
        self.0.transact(move |conn| {
            let mut stmt = conn.prepare_cached(formatcp!(
                "DELETE FROM {DKVCACHE} WHERE {EXPIRE_AT} <= ?1 RETURNING {KEY}, {EXPIRE_AT}"
            ))?;
            let mut rows = stmt.query([encode_timestamp(now)])?;
            while let Some(row) = rows.next()? {
                let key = to_bytes(row.get_ref(0)?);
                let expire_at = decode_expire_at(row.get(1)?).unwrap();
                tracing::info!(key = %key.escape_ascii(), %expire_at, "expire");
            }
            Ok(())
        })
    }

    pub fn get(&self, key: &[u8]) -> Result<Option<Entry>, Error> {
        let Some((entry, rowid)) = self
            .0
            .connect()?
            .prepare_cached(formatcp!(
                "SELECT {VALUE}, {EXPIRE_AT}, {ROWID} FROM {DKVCACHE} WHERE {KEY} = ?1"
            ))
            .and_then(|mut stmt| stmt.query_row([key], decode_entry_and_rowid))
            .optional()?
        else {
            return Ok(None);
        };
        self.0.update_recency(rowid);
        Ok(Some(entry))
    }

    /// Similar to `get`, except that it does not update a cache entry's recency.
    pub fn peek(&self, key: &[u8]) -> Result<Option<Entry>, Error> {
        Self::query_peek(self.0.connect()?, key)
    }

    fn query_peek<C>(conn: C, key: &[u8]) -> Result<Option<Entry>, Error>
    where
        C: Deref<Target = Connection>,
    {
        conn.prepare_cached(formatcp!(
            "SELECT {VALUE}, {EXPIRE_AT} FROM {DKVCACHE} WHERE {KEY} = ?1"
        ))
        .and_then(|mut stmt| stmt.query_row([key], decode_entry))
        .optional()
    }

    /// Similar to `set`, but does not update an existing entry.
    pub fn create(
        &self,
        key: &[u8],
        value: &[u8],
        expire_at: Option<Timestamp>,
    ) -> Result<Option<Entry>, Error> {
        self.0.transact(move |conn| {
            let entry = Self::query_peek(conn, key)?;
            conn.prepare_cached(formatcp!(
                "INSERT OR IGNORE INTO {DKVCACHE} ({KEY}, {VALUE}, {EXPIRE_AT}, {RECENCY})
                VALUES (?1, ?2, ?3, ?4)"
            ))?
            .execute((
                key,
                value,
                encode_expire_at(expire_at),
                encode_timestamp(Timestamp::now()),
            ))?;
            Ok(entry)
        })
    }

    pub fn set(
        &self,
        key: &[u8],
        value: &[u8],
        expire_at: Option<Timestamp>,
    ) -> Result<Option<Entry>, Error> {
        self.0.transact(move |conn| {
            let entry = Self::query_peek(conn, key)?;
            conn.prepare_cached(formatcp!(
                "INSERT OR REPLACE INTO {DKVCACHE} ({KEY}, {VALUE}, {EXPIRE_AT}, {RECENCY})
                VALUES (?1, ?2, ?3, ?4)"
            ))?
            .execute((
                key,
                value,
                encode_expire_at(expire_at),
                encode_timestamp(Timestamp::now()),
            ))?;
            Ok(entry)
        })
    }

    pub fn update(
        &self,
        key: &[u8],
        value: Option<&[u8]>,
        expire_at: Option<Option<Timestamp>>,
    ) -> Result<Option<Entry>, Error> {
        self.0.transact(move |conn| {
            let Some((entry, rowid)) = conn
                .prepare_cached(formatcp!(
                    "UPDATE {DKVCACHE} SET {RECENCY} = ?2 WHERE {KEY} = ?1
                    RETURNING {VALUE}, {EXPIRE_AT}, {ROWID}"
                ))?
                .query_row(
                    (key, encode_timestamp(Timestamp::now())),
                    decode_entry_and_rowid,
                )
                .optional()?
            else {
                return Ok(None);
            };

            if let Some(value) = value {
                conn.prepare_cached(formatcp!(
                    "UPDATE {DKVCACHE} SET {VALUE} = ?2 WHERE {ROWID} = ?1"
                ))?
                .execute((rowid, value))?;
            }
            if let Some(expire_at) = expire_at {
                conn.prepare_cached(formatcp!(
                    "UPDATE {DKVCACHE} SET {EXPIRE_AT} = ?2 WHERE {ROWID} = ?1"
                ))?
                .execute((rowid, encode_expire_at(expire_at)))?;
            }

            Ok(Some(entry))
        })
    }

    pub fn remove(&self, key: &[u8]) -> Result<Option<Entry>, Error> {
        self.0.transact(move |conn| {
            conn.prepare_cached(formatcp!(
                "DELETE FROM {DKVCACHE} WHERE {KEY} = ?1 RETURNING {VALUE}, {EXPIRE_AT}"
            ))?
            .query_row([key], decode_entry)
            .optional()
        })
    }

    pub fn remove_many<'a>(
        &self,
        keys: impl IntoIterator<Item = &'a [u8]>,
    ) -> Result<usize, Error> {
        self.0.transact(move |conn| {
            let mut stmt =
                conn.prepare_cached(formatcp!("DELETE FROM {DKVCACHE} WHERE {KEY} = ?1"))?;
            let mut num_removed = 0;
            for key in keys.into_iter() {
                num_removed += stmt.execute([key])?;
            }
            Ok(num_removed)
        })
    }
}

impl Drop for StorageImpl {
    fn drop(&mut self) {
        if let Err(error) = self.flush() {
            tracing::warn!(%error, "flush");
        }
    }
}

impl StorageImpl {
    fn new<P>(path: P) -> Self
    where
        P: AsRef<Path>,
    {
        let connection_pool_size = *connection_pool_size();
        Self {
            path: path.as_ref().to_path_buf(),
            pool: Mutex::new(Vec::with_capacity(connection_pool_size)),
            connection_pool_size,
            // NOTE: You must call `init` to initialize `len_cache` and `next_expire_at_cache`.
            len_cache: Mutex::new(0),
            next_expire_at_cache: Mutex::new(None),
            recency_buffer: Mutex::new(Vec::new()),
        }
    }

    fn connect(&self) -> Result<ConnGuard, Error> {
        let conn = match self.pool.must_lock().pop() {
            Some(conn) => conn,
            None => self.new_conn()?,
        };
        Ok(scopeguard::guard(conn, |conn| {
            let mut pool = self.pool.must_lock();
            if pool.len() < self.connection_pool_size {
                pool.push(conn);
            }
        }))
    }

    fn new_conn(&self) -> Result<Connection, Error> {
        let conn = Connection::open(&self.path)?;
        // This should be enough to "cache" all queries.
        conn.set_prepared_statement_cache_capacity(32);
        Ok(conn)
    }

    fn init(&self) -> Result<(), Error> {
        let conn = self.connect()?;
        conn.pragma_update(None, "journal_mode", "WAL")?;
        conn.execute_batch(include_str!("../schema/dkvcache/storage.sql"))?;
        *self.len_cache.must_lock() = Self::query_len(&conn)?;
        *self.next_expire_at_cache.must_lock() = Self::query_next_expire_at(&conn)?;
        Ok(())
    }

    fn transact<T, F>(&self, execute: F) -> Result<T, Error>
    where
        F: FnOnce(&Connection) -> Result<T, Error>,
    {
        let mut recency_buffer = scopeguard::guard(
            mem::take(&mut *self.recency_buffer.must_lock()),
            |mut recency_buffer| {
                if !recency_buffer.is_empty() {
                    self.recency_buffer.must_lock().append(&mut recency_buffer);
                }
            },
        );

        let mut conn = self.connect()?;
        let tx = conn.transaction()?;

        Self::execute_flush(&tx, &recency_buffer)?;

        let value = execute(&tx)?;

        let len = Self::query_len(&tx)?;
        let next_expire_at = Self::query_next_expire_at(&tx)?;

        tx.commit()?;
        recency_buffer.clear();
        drop(recency_buffer);
        *self.len_cache.must_lock() = len;
        *self.next_expire_at_cache.must_lock() = next_expire_at;

        Ok(value)
    }

    fn query_len(conn: &Connection) -> Result<usize, Error> {
        conn.prepare_cached(formatcp!("SELECT count(*) FROM {DKVCACHE}"))
            .and_then(|mut stmt| stmt.query_row([], |row| row.get(0)))
    }

    fn query_next_expire_at(conn: &Connection) -> Result<Option<Timestamp>, Error> {
        conn.prepare_cached(formatcp!("SELECT min({EXPIRE_AT}) FROM {DKVCACHE}"))
            .and_then(|mut stmt| stmt.query_row([], |row| row.get(0).map(decode_expire_at)))
    }

    fn execute_flush(
        conn: &Connection,
        recency_buffer: &[(RowId, RawTimestamp)],
    ) -> Result<(), Error> {
        let mut stmt = conn.prepare_cached(formatcp!(
            "UPDATE {DKVCACHE} SET {RECENCY} = ?2 WHERE {ROWID} = ?1 AND {RECENCY} < ?2"
        ))?;
        for (rowid, recency) in recency_buffer {
            stmt.execute([*rowid, *recency])?;
        }
        Ok(())
    }

    fn flush(&self) -> Result<(), Error> {
        // An empty transaction merely flushes `recency_buffer`.
        self.transact(|_| Ok(()))
    }

    fn update_recency(&self, rowid: RowId) {
        self.recency_buffer
            .must_lock()
            .push((rowid, encode_timestamp(Timestamp::now())));
    }
}

fn to_bytes(bytes: ValueRef) -> &[u8] {
    match bytes {
        ValueRef::Blob(bytes) => bytes,
        _ => std::panic!("expect blob value"),
    }
}

fn decode_entry(row: &Row) -> Result<Entry, Error> {
    Ok(Entry {
        value: decode_bytes(row.get(0)?),
        expire_at: decode_expire_at(row.get(1)?),
    })
}

fn decode_entry_and_rowid(row: &Row) -> Result<(Entry, RowId), Error> {
    Ok((decode_entry(row)?, row.get(2)?))
}

fn decode_bytes(bytes: Vec<u8>) -> Bytes {
    bytes.into()
}

fn decode_expire_at(expire_at: Option<RawTimestamp>) -> Option<Timestamp> {
    expire_at.map(decode_timestamp)
}

fn encode_expire_at(expire_at: Option<Timestamp>) -> Option<RawTimestamp> {
    expire_at.map(encode_timestamp)
}

fn decode_timestamp(timestamp: RawTimestamp) -> Timestamp {
    Timestamp::from_timestamp_nanos(timestamp)
}

fn encode_timestamp(timestamp: Timestamp) -> RawTimestamp {
    timestamp.timestamp_nanos_opt().unwrap()
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl Storage {
        pub fn insert_many<I>(&self, testdata: I) -> Result<(), Error>
        where
            I: Iterator<Item = (RowId, Bytes, Bytes, Option<RawTimestamp>, RawTimestamp)>,
        {
            self.0.transact(move |conn| {
                let mut stmt = conn.prepare_cached(formatcp!(
                    "INSERT OR REPLACE INTO {DKVCACHE}
                    ({ROWID}, {KEY}, {VALUE}, {EXPIRE_AT}, {RECENCY})
                    VALUES (?1, ?2, ?3, ?4, ?5)"
                ))?;
                for (rowid, key, value, expire_at, recency) in testdata {
                    stmt.execute((rowid, key.as_ref(), value.as_ref(), expire_at, recency))?;
                }
                Ok(())
            })
        }

        pub fn assert<const N: usize>(
            &self,
            expect: [(&[u8], &[u8], Option<Timestamp>); N],
        ) -> Result<(), Error> {
            self.assert_owned(
                expect
                    .into_iter()
                    .map(|(key, value, expire_at)| {
                        (
                            Bytes::copy_from_slice(key),
                            Bytes::copy_from_slice(value),
                            expire_at,
                        )
                    })
                    .collect(),
            )
        }

        pub fn assert_owned(
            &self,
            expect: Vec<(Bytes, Bytes, Option<Timestamp>)>,
        ) -> Result<(), Error> {
            let actual: Vec<_> = self
                .0
                .connect()?
                .prepare_cached(formatcp!(
                    "SELECT {KEY}, {VALUE}, {EXPIRE_AT} FROM {DKVCACHE} ORDER BY {RECENCY} ASC"
                ))?
                .query_map([], |row| {
                    Ok((
                        decode_bytes(row.get(0)?),
                        decode_bytes(row.get(1)?),
                        decode_expire_at(row.get(2)?),
                    ))
                })?
                .try_collect()?;
            assert_eq!(actual, expect);

            assert_eq!(self.is_empty(), expect.is_empty());
            assert_eq!(self.len(), expect.len());

            assert_eq!(
                self.next_expire_at(),
                expect
                    .iter()
                    .filter_map(|(_, _, expire_at)| *expire_at)
                    .min(),
            );

            Ok(())
        }

        pub fn assert_scan<const N: usize>(&self, expect: [&[u8]; N]) -> Result<(), Error> {
            self.assert_scan_owned(expect.into_iter().map(Bytes::copy_from_slice).collect())
        }

        pub fn assert_scan_owned(&self, mut expect: Vec<Bytes>) -> Result<(), Error> {
            let actual: Vec<_> = self.scan(false).try_collect()?;
            assert_eq!(actual, expect);

            let actual: Vec<_> = self.scan(true).try_collect()?;
            expect.reverse();
            assert_eq!(actual, expect);

            Ok(())
        }
    }
}

#[cfg(test)]
mod tests {
    use std::cmp;

    use tempfile::NamedTempFile;

    use super::*;

    fn e(value: &'static [u8], expire_at: Option<Timestamp>) -> Entry {
        Entry {
            value: Bytes::from_static(value),
            expire_at,
        }
    }

    #[test]
    fn open() -> Result<(), Error> {
        let t = decode_timestamp(0);

        let temp = NamedTempFile::new().unwrap();

        {
            let storage = Storage::open(temp.path())?;
            storage.assert([])?;

            assert_eq!(storage.create(b"x", b"1", Some(t))?, None);
            assert_eq!(storage.create(b"y", b"2", None)?, None);
            storage.assert([(b"x", b"1", Some(t)), (b"y", b"2", None)])?;
        }

        {
            let storage = Storage::open(temp.path())?;
            storage.assert([(b"x", b"1", Some(t)), (b"y", b"2", None)])?;

            assert_eq!(storage.get(b"x")?, Some(e(b"1", Some(t))));
            assert_eq!(storage.0.recency_buffer.must_lock().len(), 1);
            storage.assert([(b"x", b"1", Some(t)), (b"y", b"2", None)])?;
        }

        {
            let storage = Storage::open(temp.path())?;
            storage.assert([(b"y", b"2", None), (b"x", b"1", Some(t))])?;
        }

        Ok(())
    }

    #[test]
    fn scan() -> Result<(), Error> {
        let temp = NamedTempFile::new().unwrap();
        let storage = Storage::open(temp.path())?;
        storage.assert([])?;
        storage.assert_scan([])?;

        assert_eq!(storage.create(b"x", b"1", None)?, None);
        assert_eq!(storage.create(b"y", b"2", None)?, None);
        assert_eq!(storage.create(b"z", b"3", None)?, None);
        storage.assert([(b"x", b"1", None), (b"y", b"2", None), (b"z", b"3", None)])?;
        assert_eq!(storage.0.recency_buffer.must_lock().len(), 0);

        storage.assert_scan([b"x", b"y", b"z"])?;
        storage.assert([(b"x", b"1", None), (b"y", b"2", None), (b"z", b"3", None)])?;
        assert_eq!(storage.0.recency_buffer.must_lock().len(), 0);

        assert_eq!(storage.get(b"y")?, Some(e(b"2", None)));
        assert_eq!(storage.get(b"x")?, Some(e(b"1", None)));
        assert_eq!(storage.get(b"y")?, Some(e(b"2", None)));
        storage.assert([(b"x", b"1", None), (b"y", b"2", None), (b"z", b"3", None)])?;
        assert_eq!(storage.0.recency_buffer.must_lock().len(), 3);

        storage.assert_scan([b"z", b"x", b"y"])?;
        storage.assert([(b"z", b"3", None), (b"x", b"1", None), (b"y", b"2", None)])?;
        assert_eq!(storage.0.recency_buffer.must_lock().len(), 0);

        Ok(())
    }

    #[test]
    fn evict() -> Result<(), Error> {
        let temp = NamedTempFile::new().unwrap();
        let storage = Storage::open(temp.path())?;
        storage.assert([])?;

        assert_eq!(storage.evict(10)?, 0);
        storage.assert([])?;

        for i in 0..3 {
            let data = Bytes::from(format!("{i}"));
            assert_eq!(storage.create(&data, &data, None)?, None);
        }
        storage.assert([(b"0", b"0", None), (b"1", b"1", None), (b"2", b"2", None)])?;

        assert_eq!(storage.evict(10)?, 3);
        storage.assert([(b"0", b"0", None), (b"1", b"1", None), (b"2", b"2", None)])?;

        assert_eq!(storage.evict(1)?, 1);
        storage.assert([(b"2", b"2", None)])?;

        assert_eq!(storage.evict(0)?, 0);
        storage.assert([])?;

        Ok(())
    }

    #[test]
    fn expire() -> Result<(), Error> {
        let t_neg1 = decode_timestamp(-1);
        let t0 = decode_timestamp(0);
        let t1 = decode_timestamp(1);
        let t2 = decode_timestamp(2);
        let t3 = decode_timestamp(3);

        let temp = NamedTempFile::new().unwrap();
        let storage = Storage::open(temp.path())?;
        storage.assert([])?;

        assert_eq!(storage.next_expire_at(), None);

        for _ in 0..3 {
            storage.expire(t3)?;
            storage.assert([])?;
        }

        let data = Bytes::from_static(b"none");
        assert_eq!(storage.create(&data, &data, None)?, None);
        assert_eq!(storage.next_expire_at(), None);

        let mut min_t = t3;
        for t in [t1, t0, t2, t_neg1] {
            let data = Bytes::from(format!("{}", encode_timestamp(t)));
            min_t = cmp::min(min_t, t);
            assert_eq!(storage.create(&data, &data, Some(t))?, None);
            assert_eq!(storage.next_expire_at(), Some(min_t));
        }
        storage.assert([
            (b"none", b"none", None),
            (b"1", b"1", Some(t1)),
            (b"0", b"0", Some(t0)),
            (b"2", b"2", Some(t2)),
            (b"-1", b"-1", Some(t_neg1)),
        ])?;

        storage.expire(t0)?;
        storage.assert([
            (b"none", b"none", None),
            (b"1", b"1", Some(t1)),
            (b"2", b"2", Some(t2)),
        ])?;

        for _ in 0..3 {
            storage.expire(t3)?;
            storage.assert([(b"none", b"none", None)])?;
        }

        Ok(())
    }

    #[test]
    fn get_and_peek() -> Result<(), Error> {
        let t1000 = decode_timestamp(1000);

        let temp = NamedTempFile::new().unwrap();
        let storage = Storage::open(temp.path())?;
        storage.assert([])?;
        assert_eq!(storage.0.recency_buffer.must_lock().len(), 0);

        assert_eq!(storage.get(b"x")?, None);
        assert_eq!(storage.peek(b"x")?, None);

        assert_eq!(storage.create(b"x", b"1", Some(t1000))?, None);
        assert_eq!(storage.create(b"y", b"2", None)?, None);
        assert_eq!(storage.create(b"z", b"3", None)?, None);
        storage.assert([
            (b"x", b"1", Some(t1000)),
            (b"y", b"2", None),
            (b"z", b"3", None),
        ])?;
        assert_eq!(storage.0.recency_buffer.must_lock().len(), 0);

        assert_eq!(storage.get(b"w")?, None);
        assert_eq!(storage.0.recency_buffer.must_lock().len(), 0);

        assert_eq!(storage.get(b"y")?, Some(e(b"2", None)));
        assert_eq!(storage.0.recency_buffer.must_lock().len(), 1);
        assert_eq!(storage.get(b"x")?, Some(e(b"1", Some(t1000))));
        assert_eq!(storage.0.recency_buffer.must_lock().len(), 2);
        assert_eq!(storage.get(b"y")?, Some(e(b"2", None)));
        assert_eq!(storage.0.recency_buffer.must_lock().len(), 3);
        storage.assert([
            (b"x", b"1", Some(t1000)),
            (b"y", b"2", None),
            (b"z", b"3", None),
        ])?;

        storage.0.flush()?;
        assert_eq!(storage.0.recency_buffer.must_lock().len(), 0);
        storage.assert([
            (b"z", b"3", None),
            (b"x", b"1", Some(t1000)),
            (b"y", b"2", None),
        ])?;

        assert_eq!(storage.peek(b"w")?, None);
        assert_eq!(storage.peek(b"z")?, Some(e(b"3", None)));
        assert_eq!(storage.0.recency_buffer.must_lock().len(), 0);

        Ok(())
    }

    #[test]
    fn create() -> Result<(), Error> {
        let temp = NamedTempFile::new().unwrap();
        let storage = Storage::open(temp.path())?;
        storage.assert([])?;

        assert_eq!(storage.create(b"x", b"1", None)?, None);
        assert_eq!(storage.create(b"y", b"2", None)?, None);
        storage.assert([(b"x", b"1", None), (b"y", b"2", None)])?;

        assert_eq!(storage.create(b"x", b"3", None)?, Some(e(b"1", None)));
        storage.assert([(b"x", b"1", None), (b"y", b"2", None)])?;

        Ok(())
    }

    #[test]
    fn set() -> Result<(), Error> {
        let temp = NamedTempFile::new().unwrap();
        let storage = Storage::open(temp.path())?;
        storage.assert([])?;

        assert_eq!(storage.set(b"x", b"1", None)?, None);
        assert_eq!(storage.set(b"y", b"2", None)?, None);
        storage.assert([(b"x", b"1", None), (b"y", b"2", None)])?;

        assert_eq!(storage.set(b"x", b"3", None)?, Some(e(b"1", None)));
        storage.assert([(b"y", b"2", None), (b"x", b"3", None)])?;

        Ok(())
    }

    #[test]
    fn update() -> Result<(), Error> {
        let t = decode_timestamp(1);

        let temp = NamedTempFile::new().unwrap();
        let storage = Storage::open(temp.path())?;
        storage.assert([])?;

        assert_eq!(storage.update(b"x", Some(b"1"), None)?, None);
        storage.assert([])?;

        assert_eq!(storage.set(b"x", b"1", None)?, None);
        assert_eq!(storage.set(b"y", b"2", Some(t))?, None);
        storage.assert([(b"x", b"1", None), (b"y", b"2", Some(t))])?;

        assert_eq!(storage.update(b"x", Some(b"3"), None)?, Some(e(b"1", None)));
        storage.assert([(b"y", b"2", Some(t)), (b"x", b"3", None)])?;

        assert_eq!(
            storage.update(b"y", None, Some(None))?,
            Some(e(b"2", Some(t))),
        );
        storage.assert([(b"x", b"3", None), (b"y", b"2", None)])?;

        assert_eq!(storage.update(b"x", None, None)?, Some(e(b"3", None)));
        storage.assert([(b"y", b"2", None), (b"x", b"3", None)])?;

        Ok(())
    }

    #[test]
    fn remove() -> Result<(), Error> {
        let temp = NamedTempFile::new().unwrap();
        let storage = Storage::open(temp.path())?;
        storage.assert([])?;

        assert_eq!(storage.remove(b"x")?, None);
        storage.assert([])?;

        assert_eq!(storage.set(b"x", b"1", None)?, None);
        assert_eq!(storage.set(b"y", b"2", None)?, None);
        storage.assert([(b"x", b"1", None), (b"y", b"2", None)])?;

        assert_eq!(storage.remove(b"x")?, Some(e(b"1", None)));
        storage.assert([(b"y", b"2", None)])?;

        Ok(())
    }

    #[test]
    fn remove_many() -> Result<(), Error> {
        let temp = NamedTempFile::new().unwrap();
        let storage = Storage::open(temp.path())?;
        storage.assert([])?;

        assert_eq!(storage.remove_many([b"x".as_slice(), b"y"])?, 0);

        assert_eq!(storage.set(b"x", b"1", None)?, None);
        assert_eq!(storage.set(b"y", b"2", None)?, None);
        assert_eq!(storage.set(b"z", b"3", None)?, None);
        storage.assert([(b"x", b"1", None), (b"y", b"2", None), (b"z", b"3", None)])?;

        assert_eq!(storage.remove_many([b"x".as_slice(), b"y", b"w"])?, 2);
        storage.assert([(b"z", b"3", None)])?;

        Ok(())
    }
}
