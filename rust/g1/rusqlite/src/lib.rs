#![allow(incomplete_features)]
#![feature(lazy_type_alias)]
#![feature(type_alias_impl_trait)]

use std::marker::PhantomData;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use rusqlite::{Connection, Error, OpenFlags};
use scopeguard::{Always, ScopeGuard};

use g1_base::sync::MutexExt;

#[derive(Debug)]
pub struct Pool<O> {
    pool: Mutex<Vec<Connection>>,
    size: usize,

    path: PathBuf,
    _open: PhantomData<O>,
}

pub type ConnGuard<'a, O>
    = ScopeGuard<Connection, impl FnOnce(Connection) + 'a, Always>
where
    O: Open + 'a;

// We derive `Clone` for common `Open` types such as `ReadOnly`, so that `Clone` can be derived for
// generic types that are parameterized by `O: Open`.
#[derive(Clone, Debug)]
pub struct ReadOnly;

#[derive(Clone, Debug)]
pub struct ReadWrite;

#[derive(Clone, Debug)]
pub struct Apply<O, I>(PhantomData<O>, PhantomData<I>);

pub trait Open {
    fn open<P>(path: P) -> Result<Connection, Error>
    where
        P: AsRef<Path>;

    fn create<C>(conn: &Connection) -> Result<(), Error>
    where
        C: Create;
}

// I do not know if this is a good idea, but we use traits (`Init` and `Create`) to emulate
// function pointers as const generics.
pub trait Init {
    fn init(conn: &Connection) -> Result<(), Error>;
}

pub trait Create {
    fn create(conn: &Connection) -> Result<(), Error>;
}

impl<O> Pool<O>
where
    O: Open,
{
    pub fn open<C>(path: PathBuf) -> Result<Self, Error>
    where
        C: Create,
    {
        Self::with_size::<C>(path, 16)
    }

    pub fn with_size<C>(path: PathBuf, size: usize) -> Result<Self, Error>
    where
        C: Create,
    {
        let this = Self::new(path, size);
        O::create::<C>(&*this.connect()?)?;
        Ok(this)
    }

    fn new(path: PathBuf, size: usize) -> Self {
        Self {
            pool: Mutex::new(Vec::with_capacity(size)),
            size,

            path,
            _open: PhantomData,
        }
    }

    pub fn connect(&self) -> Result<ConnGuard<'_, O>, Error> {
        let conn = match self.pool.must_lock().pop() {
            Some(conn) => conn,
            None => O::open(&self.path)?,
        };
        Ok(scopeguard::guard(conn, |conn| {
            let mut pool = self.pool.must_lock();
            if pool.len() < self.size {
                pool.push(conn);
            }
        }))
    }
}

impl Open for ReadOnly {
    fn open<P>(path: P) -> Result<Connection, Error>
    where
        P: AsRef<Path>,
    {
        let conn = Connection::open_with_flags(
            path,
            OpenFlags::SQLITE_OPEN_READ_ONLY
                | OpenFlags::SQLITE_OPEN_URI
                | OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )?;

        // [SQLite] is unclear about whether `query_only` affects only this connection or all
        // connections.  Based on my tests, it seems that it affects only this connection.
        //
        // [SQLite]: https://sqlite.org/pragma.html#pragma_query_only
        conn.pragma_update(None, "query_only", true)?;

        Ok(conn)
    }

    fn create<C>(_: &Connection) -> Result<(), Error>
    where
        C: Create,
    {
        // Skip `create` in read-only databases.
        Ok(())
    }
}

impl Open for ReadWrite {
    fn open<P>(path: P) -> Result<Connection, Error>
    where
        P: AsRef<Path>,
    {
        let conn = Connection::open(path)?;

        // [rusqlite] sets `SQLITE_DEFAULT_FOREIGN_KEYS`, so we do not need to set the
        // `foreign_keys` pragma, but it is nice to do so.
        //
        // [SQLite] states that `foreign_keys` affects only this connection.
        //
        // [rusqlite]: https://github.com/rusqlite/rusqlite/blob/master/libsqlite3-sys/build.rs#L123
        // [SQLite]: https://sqlite.org/pragma.html#pragma_foreign_keys
        conn.pragma_update(None, "foreign_keys", true)?;

        Ok(conn)
    }

    fn create<C>(conn: &Connection) -> Result<(), Error>
    where
        C: Create,
    {
        C::create(conn)
    }
}

impl<O, I> Open for Apply<O, I>
where
    O: Open,
    I: Init,
{
    fn open<P>(path: P) -> Result<Connection, Error>
    where
        P: AsRef<Path>,
    {
        let conn = O::open(path)?;
        I::init(&conn)?;
        Ok(conn)
    }

    fn create<C>(conn: &Connection) -> Result<(), Error>
    where
        C: Create,
    {
        O::create::<C>(conn)
    }
}
