use bytes::Bytes;
use const_format::formatcp;
use rusqlite::Error;

use crate::{decode_bytes, RawTimestamp, RowId, Storage, DKVCACHE, KEY, RECENCY, ROWID};

/// Paginated scanner.
#[derive(Debug)]
pub(crate) struct Scanner {
    storage: Storage,
    queries: &'static [&'static str],
    state: usize,
    pagination: Pagination,
}

pub(crate) type Keys = Vec<Result<Bytes, Error>>;

type Pagination = Option<(RawTimestamp, RowId)>;

macro_rules! query_start {
    ($order:expr $(,)?) => {
        formatcp!(
            "SELECT {KEY}, {RECENCY}, {ROWID} FROM {DKVCACHE}
            ORDER BY {RECENCY} {0}, {ROWID} {0}
            LIMIT {CHUNK_SIZE}",
            $order,
        )
    };
}
macro_rules! query_next_page {
    ($order:expr, $op:expr $(,)?) => {
        formatcp!(
            "SELECT {KEY}, {RECENCY}, {ROWID} FROM {DKVCACHE}
            WHERE {RECENCY} {1} ?1
            ORDER BY {RECENCY} {0}, {ROWID} {0}
            LIMIT {CHUNK_SIZE}",
            $order,
            $op,
        )
    };
}
macro_rules! query_this_page {
    ($order:expr, $op:expr $(,)?) => {
        formatcp!(
            "SELECT {KEY}, {RECENCY}, {ROWID} FROM {DKVCACHE}
            WHERE {RECENCY} = ?1 AND {ROWID} {1} ?2
            ORDER BY {ROWID} {0}
            LIMIT {CHUNK_SIZE}",
            $order,
            $op,
        )
    };
}

const CHUNK_SIZE: usize = 1024;

const LEAST_RECENT: &[&str] = &[
    query_start!("ASC"),
    query_next_page!("ASC", ">"),
    query_this_page!("ASC", ">"),
];
const MOST_RECENT: &[&str] = &[
    query_start!("DESC"),
    query_next_page!("DESC", "<"),
    query_this_page!("DESC", "<"),
];

const STATE_START: usize = 0;
const STATE_NEXT_PAGE: usize = 1;
const STATE_THIS_PAGE: usize = 2;
const STATE_END: usize = 3;

impl Scanner {
    pub(crate) fn new(storage: Storage, most_recent: bool) -> Self {
        Self {
            storage,
            queries: if most_recent {
                MOST_RECENT
            } else {
                LEAST_RECENT
            },
            state: STATE_START,
            pagination: None,
        }
    }

    fn query(&self) -> Result<Option<(Keys, Pagination)>, Error> {
        if self.state == STATE_START {
            self.storage.0.flush()?;
        }

        let Some(query) = self.queries.get(self.state) else {
            return Ok(None);
        };

        let conn = self.storage.0.pool.connect()?;
        let mut stmt = conn.prepare_cached(query)?;
        let mut rows = match self.state {
            STATE_START => stmt.query([]),
            STATE_NEXT_PAGE => stmt.query([self.pagination.unwrap().0]),
            STATE_THIS_PAGE => stmt.query(self.pagination.unwrap()),
            _ => std::unreachable!(),
        }?;

        let mut keys = Vec::new();
        let mut pagination = None;
        while let Some(row) = rows.next()? {
            keys.push(Ok(decode_bytes(row.get(0)?)));
            pagination = Some((row.get(1)?, row.get(2)?));
        }

        Ok(Some((keys, pagination)))
    }

    fn next_state(&self, pagination: Pagination) -> (usize, Pagination) {
        (
            match (self.state, pagination) {
                (STATE_START, Some(_)) => STATE_THIS_PAGE,
                (STATE_START, None) => STATE_END,
                (STATE_NEXT_PAGE, Some(_)) => STATE_THIS_PAGE,
                (STATE_NEXT_PAGE, None) => STATE_END,
                (STATE_THIS_PAGE, Some(_)) => STATE_THIS_PAGE,
                (STATE_THIS_PAGE, None) => STATE_NEXT_PAGE,
                _ => std::unreachable!(),
            },
            pagination.or(self.pagination),
        )
    }
}

impl Iterator for Scanner {
    type Item = Keys;

    fn next(&mut self) -> Option<Self::Item> {
        match self.query() {
            Ok(Some((keys, pagination))) => {
                (self.state, self.pagination) = self.next_state(pagination);
                Some(keys)
            }
            Ok(None) => None,
            Err(error) => {
                self.state = STATE_END;
                Some(vec![Err(error)])
            }
        }
    }
}

#[cfg(test)]
mod test_harness {
    use super::*;

    impl Scanner {
        pub(crate) fn assert(&self, state: usize, pagination: Pagination) {
            assert_eq!(self.state, state);
            assert_eq!(self.pagination, pagination);
        }
    }
}

#[cfg(test)]
mod tests {
    use tempfile::NamedTempFile;

    use super::*;

    const N: usize = CHUNK_SIZE * 2 + 13;

    #[test]
    fn increasing_recency() -> Result<(), Error> {
        let keys: Vec<_> = (0..N).map(|i| Bytes::from(format!("{i}"))).collect();
        let chunk_size = i64::try_from(CHUNK_SIZE).unwrap();
        let n = i64::try_from(N).unwrap();

        let temp = NamedTempFile::new().unwrap();
        let storage = Storage::open(temp.path())?;
        storage.insert_many(keys.iter().enumerate().map(|(i, key)| {
            (
                RowId::try_from(i).unwrap(),
                key.clone(),
                key.clone(),
                None,
                RawTimestamp::try_from(i).unwrap(),
            )
        }))?;

        {
            let mut scanner = Scanner::new(storage.clone(), false);
            scanner.assert(STATE_START, None);

            assert_eq!(scanner.next().unwrap().len(), CHUNK_SIZE);
            scanner.assert(STATE_THIS_PAGE, Some((chunk_size - 1, chunk_size - 1)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_NEXT_PAGE, Some((chunk_size - 1, chunk_size - 1)));

            assert_eq!(scanner.next().unwrap().len(), CHUNK_SIZE);
            scanner.assert(
                STATE_THIS_PAGE,
                Some((chunk_size * 2 - 1, chunk_size * 2 - 1)),
            );

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(
                STATE_NEXT_PAGE,
                Some((chunk_size * 2 - 1, chunk_size * 2 - 1)),
            );

            assert_eq!(scanner.next().unwrap().len(), 13);
            scanner.assert(STATE_THIS_PAGE, Some((n - 1, n - 1)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_NEXT_PAGE, Some((n - 1, n - 1)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_END, Some((n - 1, n - 1)));

            for _ in 0..3 {
                assert_eq!(scanner.next(), None);
                scanner.assert(STATE_END, Some((n - 1, n - 1)));
            }
        }

        {
            let mut scanner = Scanner::new(storage.clone(), true);
            scanner.assert(STATE_START, None);

            assert_eq!(scanner.next().unwrap().len(), CHUNK_SIZE);
            scanner.assert(STATE_THIS_PAGE, Some((n - chunk_size, n - chunk_size)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_NEXT_PAGE, Some((n - chunk_size, n - chunk_size)));

            assert_eq!(scanner.next().unwrap().len(), CHUNK_SIZE);
            scanner.assert(
                STATE_THIS_PAGE,
                Some((n - chunk_size * 2, n - chunk_size * 2)),
            );

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(
                STATE_NEXT_PAGE,
                Some((n - chunk_size * 2, n - chunk_size * 2)),
            );

            assert_eq!(scanner.next().unwrap().len(), 13);
            scanner.assert(STATE_THIS_PAGE, Some((0, 0)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_NEXT_PAGE, Some((0, 0)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_END, Some((0, 0)));

            for _ in 0..3 {
                assert_eq!(scanner.next(), None);
                scanner.assert(STATE_END, Some((0, 0)));
            }
        }

        storage.assert_scan_owned(keys)?;

        Ok(())
    }

    #[test]
    fn decreasing_recency() -> Result<(), Error> {
        let mut keys: Vec<_> = (0..N).map(|i| Bytes::from(format!("{i}"))).collect();
        let chunk_size = i64::try_from(CHUNK_SIZE).unwrap();
        let n = i64::try_from(N).unwrap();

        let temp = NamedTempFile::new().unwrap();
        let storage = Storage::open(temp.path())?;
        storage.insert_many(keys.iter().enumerate().map(|(i, key)| {
            (
                RowId::try_from(i).unwrap(),
                key.clone(),
                key.clone(),
                None,
                RawTimestamp::try_from(N - i - 1).unwrap(),
            )
        }))?;

        {
            let mut scanner = Scanner::new(storage.clone(), false);
            scanner.assert(STATE_START, None);

            assert_eq!(scanner.next().unwrap().len(), CHUNK_SIZE);
            scanner.assert(STATE_THIS_PAGE, Some((chunk_size - 1, n - chunk_size)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_NEXT_PAGE, Some((chunk_size - 1, n - chunk_size)));

            assert_eq!(scanner.next().unwrap().len(), CHUNK_SIZE);
            scanner.assert(
                STATE_THIS_PAGE,
                Some((chunk_size * 2 - 1, n - chunk_size * 2)),
            );

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(
                STATE_NEXT_PAGE,
                Some((chunk_size * 2 - 1, n - chunk_size * 2)),
            );

            assert_eq!(scanner.next().unwrap().len(), 13);
            scanner.assert(STATE_THIS_PAGE, Some((n - 1, 0)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_NEXT_PAGE, Some((n - 1, 0)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_END, Some((n - 1, 0)));

            for _ in 0..3 {
                assert_eq!(scanner.next(), None);
                scanner.assert(STATE_END, Some((n - 1, 0)));
            }
        }

        {
            let mut scanner = Scanner::new(storage.clone(), true);
            scanner.assert(STATE_START, None);

            assert_eq!(scanner.next().unwrap().len(), CHUNK_SIZE);
            scanner.assert(STATE_THIS_PAGE, Some((n - chunk_size, chunk_size - 1)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_NEXT_PAGE, Some((n - chunk_size, chunk_size - 1)));

            assert_eq!(scanner.next().unwrap().len(), CHUNK_SIZE);
            scanner.assert(
                STATE_THIS_PAGE,
                Some((n - chunk_size * 2, chunk_size * 2 - 1)),
            );

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(
                STATE_NEXT_PAGE,
                Some((n - chunk_size * 2, chunk_size * 2 - 1)),
            );

            assert_eq!(scanner.next().unwrap().len(), 13);
            scanner.assert(STATE_THIS_PAGE, Some((0, n - 1)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_NEXT_PAGE, Some((0, n - 1)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_END, Some((0, n - 1)));

            for _ in 0..3 {
                assert_eq!(scanner.next(), None);
                scanner.assert(STATE_END, Some((0, n - 1)));
            }
        }

        keys.reverse();
        storage.assert_scan_owned(keys)?;

        Ok(())
    }

    #[test]
    fn same_recency() -> Result<(), Error> {
        let keys: Vec<_> = (0..N).map(|i| Bytes::from(format!("{i}"))).collect();
        let chunk_size = i64::try_from(CHUNK_SIZE).unwrap();
        let n = i64::try_from(N).unwrap();

        let temp = NamedTempFile::new().unwrap();
        let storage = Storage::open(temp.path())?;
        storage.insert_many(keys.iter().enumerate().map(|(i, key)| {
            (
                RowId::try_from(i).unwrap(),
                key.clone(),
                key.clone(),
                None,
                -1234,
            )
        }))?;

        {
            let mut scanner = Scanner::new(storage.clone(), false);
            scanner.assert(STATE_START, None);

            assert_eq!(scanner.next().unwrap().len(), CHUNK_SIZE);
            scanner.assert(STATE_THIS_PAGE, Some((-1234, chunk_size - 1)));

            assert_eq!(scanner.next().unwrap().len(), CHUNK_SIZE);
            scanner.assert(STATE_THIS_PAGE, Some((-1234, chunk_size * 2 - 1)));

            assert_eq!(scanner.next().unwrap().len(), 13);
            scanner.assert(STATE_THIS_PAGE, Some((-1234, n - 1)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_NEXT_PAGE, Some((-1234, n - 1)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_END, Some((-1234, n - 1)));

            for _ in 0..3 {
                assert_eq!(scanner.next(), None);
                scanner.assert(STATE_END, Some((-1234, n - 1)));
            }
        }

        {
            let mut scanner = Scanner::new(storage.clone(), true);
            scanner.assert(STATE_START, None);

            assert_eq!(scanner.next().unwrap().len(), CHUNK_SIZE);
            scanner.assert(STATE_THIS_PAGE, Some((-1234, n - chunk_size)));

            assert_eq!(scanner.next().unwrap().len(), CHUNK_SIZE);
            scanner.assert(STATE_THIS_PAGE, Some((-1234, n - chunk_size * 2)));

            assert_eq!(scanner.next().unwrap().len(), 13);
            scanner.assert(STATE_THIS_PAGE, Some((-1234, 0)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_NEXT_PAGE, Some((-1234, 0)));

            assert_eq!(scanner.next().unwrap().len(), 0);
            scanner.assert(STATE_END, Some((-1234, 0)));

            for _ in 0..3 {
                assert_eq!(scanner.next(), None);
                scanner.assert(STATE_END, Some((-1234, 0)));
            }
        }

        storage.assert_scan_owned(keys)?;

        Ok(())
    }
}
