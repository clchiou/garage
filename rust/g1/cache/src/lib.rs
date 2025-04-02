//! LRU cache backed by an [SQLite temporary database][temp_db].
//!
//! [temp_db]: https://www.sqlite.org/inmemorydb.html#temp_db

#![allow(incomplete_features)]
#![feature(generic_const_exprs)]
#![feature(generic_const_items)]
#![feature(iter_intersperse)]
#![cfg_attr(test, feature(duration_constants))]

use std::borrow::Cow;
use std::marker::PhantomData;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use rusqlite::{Connection, Row};

use g1_base::collections::Array;
use g1_base::sync::MutexExt;
use g1_chrono::{Timestamp, TimestampExt};
use g1_rusqlite::ConnectionExt;

pub use rusqlite::types::{FromSqlError, ToSql};
pub use rusqlite::Error;

#[derive(Debug)]
pub struct LruCacheDatabase {
    // We have to share `Connection` because a temporary database is private to each connection.
    conn: Arc<Mutex<Connection>>,
    serial: AtomicU64,
}

#[derive(Debug)]
pub struct LruCache<S> {
    conn: Arc<Mutex<Connection>>,
    recency: AtomicU64,
    max_size: usize,

    num_hits: AtomicU64,
    num_misses: AtomicU64,

    len: String,
    clear: String,
    get: String,
    insert: String,
    remove: String,

    set_recency: String,

    evict: [String; 2],
    expire: Option<(String, u64)>,

    _schema: PhantomData<S>,
}

pub trait Schema {
    type Key;
    type Value;

    // TODO: Why do we need this bound?  Additionally, this bound does not guarantee that `KEY_LEN`
    // is greater than `0`.
    const KEY_TYPES: [&'static str; Self::KEY_LEN] where [(); Self::KEY_LEN]: Sized;
    const KEY_LEN: usize;

    fn encode_key(key: &Self::Key) -> [&dyn ToSql; Self::KEY_LEN];

    fn decode_value(raw: &[u8]) -> Result<Self::Value, FromSqlError>;
    fn encode_value(value: &Self::Value) -> Result<Cow<[u8]>, Error>;
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct Stat {
    pub num_hits: u64,
    pub num_misses: u64,
}

fn open_temp_db() -> Result<Connection, Error> {
    // TODO: What cache capacity should we choose?
    Connection::open("").inspect(|conn| conn.set_prepared_statement_cache_capacity(128))
}

impl LruCacheDatabase {
    pub fn open() -> Result<Self, Error> {
        open_temp_db().map(Self::new)
    }

    fn new(conn: Connection) -> Self {
        Self {
            conn: Arc::new(Mutex::new(conn)),
            serial: AtomicU64::new(0),
        }
    }

    pub fn create<S>(
        &self,
        max_size: usize,
        timeout: Option<Duration>,
    ) -> Result<LruCache<S>, Error>
    where
        S: Schema,
        [(); S::KEY_LEN + 3]: Sized,
    {
        let serial = self.serial.fetch_add(1, Ordering::SeqCst);
        let cache = LruCache::new(self.conn.clone(), serial, max_size, timeout);
        cache.create(serial)?;
        Ok(cache)
    }
}

macro_rules! params_key {
    ($key:ident $(,)?) => {
        S::encode_key($key).as_slice()
    };
}

impl<S> LruCache<S>
where
    S: Schema,
    // TODO: Why do we need this bound?  Additionally, this bound does not guarantee that `KEY_LEN`
    // is greater than `0`.
    [(); S::KEY_LEN + 3]: Sized,
{
    fn new(
        conn: Arc<Mutex<Connection>>,
        serial: u64,
        max_size: usize,
        timeout: Option<Duration>,
    ) -> Self {
        // TODO: How can we statically ensure that `KEY_LEN` is greater than `0`?
        assert!(S::KEY_LEN > 0);

        Self {
            conn,
            recency: AtomicU64::new(0),
            max_size,

            num_hits: AtomicU64::new(0),
            num_misses: AtomicU64::new(0),

            len: S::len(serial),
            clear: S::clear(serial),
            get: S::get(serial),
            insert: S::insert(serial, timeout),
            remove: S::remove(serial),

            set_recency: S::set_recency(serial),

            evict: S::evict(serial),
            expire: timeout.map(|timeout| (S::expire(serial), timeout.as_secs())),

            _schema: PhantomData,
        }
    }

    fn create(&self, serial: u64) -> Result<(), Error> {
        self.conn
            .must_lock()
            .execute_batch(&S::create_table(serial, self.expire.is_some()))
    }

    fn next_recency(&self) -> u64 {
        self.recency.fetch_add(1, Ordering::SeqCst)
    }

    fn now(&self) -> u64 {
        // We manually encode `Timestamp` (an alias for `DateTime<Utc>`) as `u64` because `ToSql`
        // encodes `DateTime<Utc>` as a string, which is quite inefficient.
        if self.expire.is_some() {
            Timestamp::now().timestamp_u64()
        } else {
            0
        }
    }

    pub fn take_stat(&self) -> Stat {
        Stat::new(
            self.num_hits.swap(0, Ordering::SeqCst),
            self.num_misses.swap(0, Ordering::SeqCst),
        )
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub fn len(&self) -> usize {
        self.try_len().expect("try_len")
    }

    pub fn try_len(&self) -> Result<usize, Error> {
        self.read(self.now(), |conn| self.query_len(conn))
    }

    fn query_len(&self, conn: &Connection) -> Result<usize, Error> {
        conn.prepare_cached(&self.len)?.query_row([], S::decode_len)
    }

    pub fn clear(&self) {
        self.try_clear().expect("try_clear")
    }

    pub fn try_clear(&self) -> Result<(), Error> {
        let _ = self
            .conn
            .must_lock()
            .prepare_cached(&self.clear)?
            .execute([])?;
        Ok(())
    }

    pub fn get(&self, key: &S::Key) -> Option<S::Value> {
        self.try_get(key).expect("try_get")
    }

    pub fn try_get(&self, key: &S::Key) -> Result<Option<S::Value>, Error> {
        self.read(self.now(), |conn| self.query_get(conn, key))
    }

    fn query_get(&self, conn: &Connection, key: &S::Key) -> Result<Option<S::Value>, Error> {
        let Some((id, value)) = conn.optional(&self.get, params_key!(key), S::decode_get)? else {
            self.num_misses.fetch_add(1, Ordering::SeqCst);
            return Ok(None);
        };

        let _ = conn
            .prepare_cached(&self.set_recency)?
            .execute([id, self.next_recency()])?;

        self.num_hits.fetch_add(1, Ordering::SeqCst);
        Ok(Some(value))
    }

    pub fn insert(&self, key: &S::Key, value: &S::Value) {
        self.try_insert(key, value).expect("try_insert")
    }

    pub fn try_insert(&self, key: &S::Key, value: &S::Value) -> Result<(), Error> {
        self.exec_insert(self.now(), key, value)
    }

    fn exec_insert(&self, now: u64, key: &S::Key, value: &S::Value) -> Result<(), Error> {
        let value = &S::encode_value(value)?;

        let mut conn = self.conn.must_lock();
        let tx = conn.transaction()?;

        tx.prepare_cached(&self.insert)?.execute(
            S::insert_params(
                key,
                &self.next_recency(),
                self.expire
                    .as_ref()
                    .map(|(_, timeout)| now + timeout)
                    .as_ref(),
                value,
            )
            .as_slice(),
        )?;

        // The order matters: we should call `expire` before `evict`.
        self.expire(&tx, now)?;
        self.evict(&tx)?;

        tx.commit()
    }

    pub fn remove(&self, key: &S::Key) -> Option<S::Value> {
        self.try_remove(key).expect("try_remove")
    }

    pub fn try_remove(&self, key: &S::Key) -> Result<Option<S::Value>, Error> {
        // Given our use case, `remove` is essentially a `read`.
        self.read(self.now(), |conn| self.query_remove(conn, key))
    }

    fn query_remove(&self, conn: &Connection, key: &S::Key) -> Result<Option<S::Value>, Error> {
        conn.optional(&self.remove, params_key!(key), S::decode_remove)
    }

    fn read<T, F>(&self, now: u64, query: F) -> Result<T, Error>
    where
        F: FnOnce(&Connection) -> Result<T, Error>,
    {
        let mut conn = self.conn.must_lock();
        let tx = conn.transaction()?;

        // We must remove expired rows before querying the table.
        self.expire(&tx, now)?;

        let value = query(&tx)?;

        tx.commit()?;
        Ok(value)
    }

    fn evict(&self, conn: &Connection) -> Result<(), Error> {
        let Some(n) = self
            .query_len(conn)?
            .checked_sub(self.max_size)
            .filter(|n| *n > 0)
        else {
            return Ok(());
        };

        let Some(recency) = conn.optional(&self.evict[0], [n], S::decode_evict)? else {
            return Ok(());
        };

        conn.prepare_cached(&self.evict[1])?.execute([recency])?;
        Ok(())
    }

    fn expire(&self, conn: &Connection, now: u64) -> Result<(), Error> {
        let Some((expire, _)) = self.expire.as_ref() else {
            return Ok(());
        };

        let _ = conn.prepare_cached(expire)?.execute([now])?;
        Ok(())
    }
}

impl Stat {
    pub fn new(num_hits: u64, num_misses: u64) -> Self {
        Self {
            num_hits,
            num_misses,
        }
    }
}

// Table and index names.
const TABLE: &str = "table";
const INDEX: &str = "index";

// Column names.
const ROWID: &str = "rowid";
const KEY: &str = "key";
const RECENCY: &str = "recency";
const EXPIRE_AT: &str = "expire_at";
const VALUE: &str = "value";

trait SchemaImpl: Schema
where
    [(); Self::KEY_LEN + 3]: Sized,
{
    fn create_table(serial: u64, has_timeout: bool) -> String {
        let mut sql = String::new();
        sql.push_str("BEGIN;\n");

        sql.push_str(&format!("CREATE TABLE IF NOT EXISTS {TABLE}_{serial} ("));
        {
            for (i, key_type) in Self::KEY_TYPES.iter().enumerate() {
                sql.push_str(&format!("{KEY}_{i} {key_type} NOT NULL, "));
            }

            sql.push_str(const_format::formatcp!("{RECENCY} INTEGER NOT NULL, "));
            if has_timeout {
                sql.push_str(const_format::formatcp!("{EXPIRE_AT} INTEGER NOT NULL, "));
            }

            sql.push_str(const_format::formatcp!("{VALUE} BLOB NOT NULL"));
        }
        sql.push_str(");\n");

        sql.push_str(&format!(
            "CREATE UNIQUE INDEX IF NOT EXISTS {INDEX}_{serial}_{KEY} ON {TABLE}_{serial} ("
        ));
        for piece in (0..Self::KEY_LEN)
            .map(|i| Cow::Owned(format!("{KEY}_{i}")))
            .intersperse(", ".into())
        {
            sql.push_str(&piece);
        }
        sql.push_str(");\n");

        sql.push_str(&format!(
            "CREATE UNIQUE INDEX IF NOT EXISTS {INDEX}_{serial}_{RECENCY} ON {TABLE}_{serial} ({RECENCY});\n",
        ));
        if has_timeout {
            sql.push_str(&format!(
                "CREATE INDEX IF NOT EXISTS {INDEX}_{serial}_{EXPIRE_AT} ON {TABLE}_{serial} ({EXPIRE_AT});\n",
            ));
        }

        sql.push_str("COMMIT;\n");
        sql
    }

    //
    // NOTE: The queries below do not exclude expired rows.  You must remove them before executing
    // these queries.
    //

    fn len(serial: u64) -> String {
        format!("SELECT count(*) FROM {TABLE}_{serial}")
    }

    fn decode_len(row: &Row) -> Result<usize, Error> {
        row.get(0)
    }

    fn clear(serial: u64) -> String {
        format!("DELETE FROM {TABLE}_{serial}")
    }

    fn get(serial: u64) -> String {
        let mut sql = format!("SELECT {ROWID}, {VALUE} FROM {TABLE}_{serial} WHERE ");
        Self::append_query_key(&mut sql);
        sql
    }

    fn decode_get(row: &Row) -> Result<(u64, Self::Value), Error> {
        Ok((row.get(0)?, Self::to_value(row, 1)?))
    }

    fn insert(serial: u64, timeout: Option<Duration>) -> String {
        let mut sql = format!("INSERT OR REPLACE INTO {TABLE}_{serial} (");
        {
            for i in 0..Self::KEY_LEN {
                sql.push_str(&format!("{KEY}_{i}, "));
            }

            sql.push_str(const_format::formatcp!("{RECENCY}, "));
            if timeout.is_some() {
                sql.push_str(const_format::formatcp!("{EXPIRE_AT}, "));
            }

            sql.push_str(const_format::formatcp!("{VALUE}"));
        }
        sql.push_str(") VALUES (");
        {
            for _ in 0..Self::KEY_LEN {
                sql.push_str("?, ");
            }

            sql.push_str("?, ");
            if timeout.is_some() {
                sql.push_str("?, ");
            }

            sql.push('?');
        }
        sql.push(')');
        sql
    }

    fn insert_params<'a>(
        key: &'a Self::Key,
        recency: &'a u64,
        expire_at: Option<&'a u64>,
        value: &'a dyn ToSql,
    ) -> Array<&'a dyn ToSql, { Self::KEY_LEN + 3 }> {
        let mut params = Array::new();
        params.extend(Self::encode_key(key));
        params.push(recency);
        if let Some(expire_at) = expire_at {
            params.push(expire_at);
        }
        params.push(value);
        params
    }

    fn remove(serial: u64) -> String {
        let mut sql = format!("DELETE FROM {TABLE}_{serial} WHERE ");
        Self::append_query_key(&mut sql);
        sql.push_str(const_format::formatcp!(" RETURNING {VALUE}"));
        sql
    }

    fn decode_remove(row: &Row) -> Result<Self::Value, Error> {
        Self::to_value(row, 0)
    }

    fn set_recency(serial: u64) -> String {
        format!("UPDATE {TABLE}_{serial} SET {RECENCY} = ?2 WHERE {ROWID} = ?1")
    }

    fn evict(serial: u64) -> [String; 2] {
        [
            // Work around the [issue] that `rusqlite` does not enable
            // `SQLITE_ENABLE_UPDATE_DELETE_LIMIT`.
            //
            // [issue]: https://github.com/rusqlite/rusqlite/issues/1111
            //
            // Note the `ASC` in the query, which is selecting the least recent entries.  Although
            // this query is a scan, it should be quite efficient because:
            // * The offset is very small due to the `evict` call on each `insert`, and
            // * The query scans through an index.
            format!(
                "SELECT {RECENCY} FROM {TABLE}_{serial} ORDER BY {RECENCY} ASC LIMIT 1 OFFSET ?",
            ),
            format!("DELETE FROM {TABLE}_{serial} WHERE {RECENCY} < ?"),
        ]
    }

    fn decode_evict(row: &Row) -> Result<u64, Error> {
        row.get(0)
    }

    fn expire(serial: u64) -> String {
        format!("DELETE FROM {TABLE}_{serial} WHERE {EXPIRE_AT} < ?")
    }

    //
    // Helpers.
    //

    fn append_query_key(sql: &mut String) {
        for piece in (0..Self::KEY_LEN)
            .map(|i| Cow::Owned(format!("{KEY}_{i} = ?")))
            .intersperse(" AND ".into())
        {
            sql.push_str(&piece);
        }
    }

    fn to_value(row: &Row, i: usize) -> Result<Self::Value, Error> {
        Ok(Self::decode_value(row.get_ref(i)?.as_blob()?)?)
    }
}

impl<S: Schema> SchemaImpl for S where [(); S::KEY_LEN + 3]: Sized {}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use super::*;

    struct TestSchema;

    impl Schema for TestSchema {
        type Key = (u8, u16);
        type Value = Vec<u8>;

        const KEY_TYPES: [&'static str; Self::KEY_LEN] = ["INTEGER", "INTEGER"];
        const KEY_LEN: usize = 2;

        fn encode_key(key: &Self::Key) -> [&dyn ToSql; Self::KEY_LEN] {
            [&key.0, &key.1]
        }

        fn decode_value(raw: &[u8]) -> Result<Self::Value, FromSqlError> {
            Ok(raw.to_vec())
        }

        fn encode_value(value: &Self::Value) -> Result<Cow<[u8]>, Error> {
            Ok(value.into())
        }
    }

    impl LruCache<TestSchema> {
        fn assert(&self, serial: u64, expect: &[(u8, u16, u64, &[u8])]) {
            let conn = self.conn.must_lock();
            assert_eq!(
                conn.vector(
                        &format!(
                            "SELECT key_0, key_1, recency, value FROM table_{serial} ORDER BY key_0, key_1 ASC",
                        ),
                        [],
                        |row| Ok((
                            row.get::<_, u8>(0)?,
                            row.get::<_, u16>(1)?,
                            row.get::<_, u64>(2)?,
                            row.get::<_, Vec<u8>>(3)?
                        )),
                    )
                    .unwrap(),
                expect
                    .iter()
                    .map(|row| (row.0, row.1, row.2, row.3.to_vec()))
                    .collect::<Vec<_>>(),
            );
            // We do not test `self.len()` here because it removes expired rows.
            assert_eq!(self.query_len(&*conn).unwrap(), expect.len());
        }

        fn assert_extra(&self, serial: u64, expect: &[(u8, u16, u64, u64, &[u8])]) {
            let conn = self.conn.must_lock();
            assert_eq!(
                conn.vector(
                        &format!(
                            "SELECT key_0, key_1, recency, expire_at, value FROM table_{serial} ORDER BY key_0, key_1 ASC",
                        ),
                        [],
                        |row| Ok((
                            row.get::<_, u8>(0)?,
                            row.get::<_, u16>(1)?,
                            row.get::<_, u64>(2)?,
                            row.get::<_, u64>(3)?,
                            row.get::<_, Vec<u8>>(4)?
                        )),
                    )
                    .unwrap(),
                expect
                    .iter()
                    .map(|row| (row.0, row.1, row.2, row.3, row.4.to_vec()))
                    .collect::<Vec<_>>(),
            );
            // We do not test `self.len()` here because it removes expired rows.
            assert_eq!(self.query_len(&*conn).unwrap(), expect.len());
        }

        fn assert_recency(&self, recency: u64) {
            assert_eq!(self.recency.load(Ordering::SeqCst), recency);
        }

        fn assert_stat(&self, num_hits: u64, num_misses: u64) {
            assert_eq!(self.num_hits.load(Ordering::SeqCst), num_hits);
            assert_eq!(self.num_misses.load(Ordering::SeqCst), num_misses);
        }
    }

    #[test]
    fn len() {
        let value = b"spam".to_vec();

        let db = LruCacheDatabase::open().unwrap();
        for (serial, timeout) in [None, Some(Duration::SECOND)].into_iter().enumerate() {
            let cache = db.create::<TestSchema>(10, timeout).unwrap();
            cache.assert(serial.try_into().unwrap(), &[]);
            assert_eq!(cache.is_empty(), true);
            assert_eq!(cache.len(), 0);

            cache.insert(&(1, 2), &value);
            assert_eq!(cache.is_empty(), false);
            assert_eq!(cache.len(), 1);

            cache.insert(&(3, 4), &value);
            assert_eq!(cache.is_empty(), false);
            assert_eq!(cache.len(), 2);

            cache.insert(&(5, 6), &value);
            assert_eq!(cache.is_empty(), false);
            assert_eq!(cache.len(), 3);

            cache.clear();
            assert_eq!(cache.is_empty(), true);
            assert_eq!(cache.len(), 0);
        }
    }

    #[test]
    fn get() {
        let value = b"spam".to_vec();

        let db = LruCacheDatabase::open().unwrap();
        for (serial, timeout) in [None, Some(Duration::SECOND)].into_iter().enumerate() {
            let cache = db.create::<TestSchema>(10, timeout).unwrap();
            let serial = u64::try_from(serial).unwrap();
            cache.assert(serial, &[]);
            cache.assert_recency(0);
            cache.assert_stat(0, 0);

            for i in 1..=3 {
                assert_eq!(cache.get(&(1, 2)), None);
                cache.assert(serial, &[]);
                cache.assert_recency(0);
                cache.assert_stat(0, i);
            }

            cache.insert(&(1, 2), &value);
            cache.insert(&(3, 4), &b"egg".to_vec());
            cache.assert(serial, &[(1, 2, 0, b"spam"), (3, 4, 1, b"egg")]);
            cache.assert_recency(2);
            cache.assert_stat(0, 3);

            let expect = Some(value.clone());
            for i in 1..=3 {
                assert_eq!(cache.get(&(1, 2)), expect);
                cache.assert(serial, &[(1, 2, i + 1, b"spam"), (3, 4, 1, b"egg")]);
                cache.assert_recency(i + 2);
                cache.assert_stat(i, 3);
            }

            assert_eq!(cache.take_stat(), Stat::new(3, 3));
            cache.assert(serial, &[(1, 2, 4, b"spam"), (3, 4, 1, b"egg")]);
            cache.assert_recency(5);
            cache.assert_stat(0, 0);
        }
    }

    #[test]
    fn insert() {
        let v1 = b"spam".to_vec();
        let v2 = b"egg".to_vec();

        let db = LruCacheDatabase::open().unwrap();
        for (serial, timeout) in [None, Some(Duration::SECOND)].into_iter().enumerate() {
            let cache = db.create::<TestSchema>(10, timeout).unwrap();
            let serial = u64::try_from(serial).unwrap();
            cache.assert(serial, &[]);
            cache.assert_recency(0);

            cache.insert(&(1, 2), &v1);
            cache.assert(serial, &[(1, 2, 0, b"spam")]);
            cache.assert_recency(1);

            cache.insert(&(1, 2), &v1);
            cache.assert(serial, &[(1, 2, 1, b"spam")]);
            cache.assert_recency(2);

            cache.insert(&(1, 2), &v2);
            cache.assert(serial, &[(1, 2, 2, b"egg")]);
            cache.assert_recency(3);

            cache.insert(&(3, 4), &v1);
            cache.assert(serial, &[(1, 2, 2, b"egg"), (3, 4, 3, b"spam")]);
            cache.assert_recency(4);
        }

        {
            let cache = db.create::<TestSchema>(1, None).unwrap();
            cache.assert(2, &[]);

            cache.insert(&(0, 0), &v1);
            cache.assert(2, &[(0, 0, 0, b"spam")]);

            for i in 1..=10 {
                cache.insert(&(i, 0), &v1);
                cache.assert(2, &[(i, 0, i.into(), b"spam")]);
            }
        }

        {
            let cache = db.create::<TestSchema>(10, Some(Duration::SECOND)).unwrap();
            cache.assert_extra(3, &[]);

            cache.exec_insert(100, &(0, 0), &v1).unwrap();
            cache.assert_extra(3, &[(0, 0, 0, 101, b"spam")]);

            for i in 1..=9 {
                let now = 100 + u64::from(i) * 2;
                cache.exec_insert(now, &(i, 0), &v1).unwrap();
                cache.assert_extra(3, &[(i, 0, i.into(), now + 1, b"spam")]);
            }
        }
    }

    #[test]
    fn remove() {
        let value = b"spam".to_vec();

        let db = LruCacheDatabase::open().unwrap();
        for (serial, timeout) in [None, Some(Duration::SECOND)].into_iter().enumerate() {
            let cache = db.create::<TestSchema>(10, timeout).unwrap();
            let serial = u64::try_from(serial).unwrap();
            cache.assert(serial, &[]);

            let expect = &[
                (0, 0, 0, b"spam" as &[u8]),
                (1, 0, 1, b"spam"),
                (2, 0, 2, b"spam"),
            ];
            for i in 0..3 {
                cache.insert(&(i, 0), &value);
            }
            cache.assert(serial, expect);

            assert_eq!(cache.remove(&(0, 0)), Some(value.clone()));
            cache.assert(serial, &expect[1..]);

            for _ in 0..3 {
                assert_eq!(cache.remove(&(0, 0)), None);
                cache.assert(serial, &expect[1..]);
            }
        }
    }

    #[test]
    fn read() {
        let value = b"spam".to_vec();

        let db = LruCacheDatabase::open().unwrap();
        let cache = db
            .create::<TestSchema>(10, Some(10 * Duration::SECOND))
            .unwrap();
        cache.assert_extra(0, &[]);

        cache.exec_insert(100, &(1, 2), &value).unwrap();
        cache.exec_insert(101, &(3, 4), &value).unwrap();
        cache.exec_insert(102, &(5, 6), &value).unwrap();

        let expect = &[
            (1, 2, 0, 110, b"spam" as &[u8]),
            (3, 4, 1, 111, b"spam"),
            (5, 6, 2, 112, b"spam"),
        ];
        cache.assert_extra(0, expect);

        for _ in 0..3 {
            assert_eq!(cache.read(110, |conn| cache.query_len(conn)).unwrap(), 3);
            cache.assert_extra(0, expect);
        }

        for _ in 0..3 {
            assert_eq!(cache.read(111, |conn| cache.query_len(conn)).unwrap(), 2);
            cache.assert_extra(0, &expect[1..]);
        }

        for _ in 0..3 {
            assert_eq!(cache.read(112, |conn| cache.query_len(conn)).unwrap(), 1);
            cache.assert_extra(0, &expect[2..]);
        }

        for _ in 0..3 {
            assert_eq!(cache.read(113, |conn| cache.query_len(conn)).unwrap(), 0);
            cache.assert_extra(0, &[]);
        }
    }

    #[test]
    fn evict() {
        let value = b"spam".to_vec();

        let db = LruCacheDatabase::open().unwrap();
        let cache = db.create::<TestSchema>(3, None).unwrap();
        cache.assert(0, &[]);
        cache.assert_recency(0);

        let mut expect = &[
            (0, 0, 0, b"spam" as &[u8]),
            (1, 0, 1, b"spam"),
            (2, 0, 2, b"spam"),
        ];
        for i in 0..3 {
            cache.insert(&(i, 0), &value);
        }
        cache.assert(0, expect);
        cache.assert_recency(3);

        for _ in 0..3 {
            cache.evict(&*cache.conn.must_lock()).unwrap();
            cache.assert(0, expect);
        }

        expect = &[(1, 0, 1, b"spam"), (2, 0, 2, b"spam"), (10, 0, 3, b"spam")];
        cache.insert(&(10, 0), &value);
        cache.assert(0, expect);
        cache.assert_recency(4);

        for _ in 0..3 {
            cache.evict(&*cache.conn.must_lock()).unwrap();
            cache.assert(0, expect);
        }

        expect = &[(2, 0, 2, b"spam"), (10, 0, 3, b"spam"), (11, 0, 4, b"spam")];
        cache.insert(&(11, 0), &value);
        cache.assert(0, expect);
        cache.assert_recency(5);

        for _ in 0..3 {
            cache.evict(&*cache.conn.must_lock()).unwrap();
            cache.assert(0, expect);
        }

        expect = &[(9, 0, 5, b"spam"), (10, 0, 3, b"spam"), (11, 0, 4, b"spam")];
        cache.insert(&(9, 0), &value);
        cache.assert(0, expect);
        cache.assert_recency(6);

        for _ in 0..3 {
            cache.evict(&*cache.conn.must_lock()).unwrap();
            cache.assert(0, expect);
        }
    }

    #[test]
    fn expire() {
        let value = b"spam".to_vec();

        let db = LruCacheDatabase::open().unwrap();
        let cache = db
            .create::<TestSchema>(10, Some(10 * Duration::SECOND))
            .unwrap();
        cache.assert_extra(0, &[]);

        let mut expect = Vec::new();
        let mut r = 0;
        for i in 0..3 {
            cache.exec_insert(100, &(1, i), &value).unwrap();
            cache.exec_insert(101, &(2, i), &value).unwrap();
            cache.exec_insert(102, &(3, i), &value).unwrap();
            expect.push((1, i, r + 0, 110, value.as_ref()));
            expect.push((2, i, r + 1, 111, value.as_ref()));
            expect.push((3, i, r + 2, 112, value.as_ref()));
            r += 3;
        }
        expect.sort_by_key(|row| (row.0, row.1));
        cache.assert_extra(0, &expect);

        for _ in 0..3 {
            cache.expire(&*cache.conn.must_lock(), 110).unwrap();
            cache.assert_extra(0, &expect);
        }

        for _ in 0..3 {
            cache.expire(&*cache.conn.must_lock(), 111).unwrap();
            cache.assert_extra(0, &expect[3..]);
        }

        for _ in 0..3 {
            cache.expire(&*cache.conn.must_lock(), 112).unwrap();
            cache.assert_extra(0, &expect[6..]);
        }

        for _ in 0..3 {
            cache.expire(&*cache.conn.must_lock(), 113).unwrap();
            cache.assert_extra(0, &[]);
        }
    }

    #[test]
    fn schema_create_table() {
        assert_eq!(
            TestSchema::create_table(999, true),
            "BEGIN;
CREATE TABLE IF NOT EXISTS table_999 (key_0 INTEGER NOT NULL, key_1 INTEGER NOT NULL, recency INTEGER NOT NULL, expire_at INTEGER NOT NULL, value BLOB NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS index_999_key ON table_999 (key_0, key_1);
CREATE UNIQUE INDEX IF NOT EXISTS index_999_recency ON table_999 (recency);
CREATE INDEX IF NOT EXISTS index_999_expire_at ON table_999 (expire_at);
COMMIT;
",
        );
        assert_eq!(
            TestSchema::create_table(999, false),
            "BEGIN;
CREATE TABLE IF NOT EXISTS table_999 (key_0 INTEGER NOT NULL, key_1 INTEGER NOT NULL, recency INTEGER NOT NULL, value BLOB NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS index_999_key ON table_999 (key_0, key_1);
CREATE UNIQUE INDEX IF NOT EXISTS index_999_recency ON table_999 (recency);
COMMIT;
",
        );
    }

    #[test]
    fn schema_len() {
        assert_eq!(TestSchema::len(0), "SELECT count(*) FROM table_0");
    }

    #[test]
    fn schema_clear() {
        assert_eq!(TestSchema::clear(0), "DELETE FROM table_0");
    }

    #[test]
    fn schema_get() {
        assert_eq!(
            TestSchema::get(0),
            "SELECT rowid, value FROM table_0 WHERE key_0 = ? AND key_1 = ?",
        );
    }

    #[test]
    fn schema_insert() {
        assert_eq!(
            TestSchema::insert(0, Some(Duration::ZERO)),
            "INSERT OR REPLACE INTO table_0 (key_0, key_1, recency, expire_at, value) VALUES (?, ?, ?, ?, ?)",
        );
        assert_eq!(
            TestSchema::insert(0, None),
            "INSERT OR REPLACE INTO table_0 (key_0, key_1, recency, value) VALUES (?, ?, ?, ?)",
        );
    }

    #[test]
    fn schema_remove() {
        assert_eq!(
            TestSchema::remove(0),
            "DELETE FROM table_0 WHERE key_0 = ? AND key_1 = ? RETURNING value",
        );
    }

    #[test]
    fn schema_set_recency() {
        assert_eq!(
            TestSchema::set_recency(0),
            "UPDATE table_0 SET recency = ?2 WHERE rowid = ?1",
        );
    }

    #[test]
    fn schema_evict() {
        assert_eq!(
            TestSchema::evict(0),
            [
                "SELECT recency FROM table_0 ORDER BY recency ASC LIMIT 1 OFFSET ?",
                "DELETE FROM table_0 WHERE recency < ?",
            ],
        );
    }

    #[test]
    fn schema_expire() {
        assert_eq!(
            TestSchema::expire(0),
            "DELETE FROM table_0 WHERE expire_at < ?",
        );
    }
}
