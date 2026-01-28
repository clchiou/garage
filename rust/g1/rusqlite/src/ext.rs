use rusqlite::{Connection, Error, OptionalExtension, Params, Row, Statement};

pub trait ConnectionExt {
    fn one_or_none<T, P, F>(&self, sql: &str, params: P, f: F) -> Result<Option<T>, Error>
    where
        P: Params,
        F: FnOnce(&Row<'_>) -> Result<T, Error>;

    fn optional<T, P, F>(&self, sql: &str, params: P, f: F) -> Result<Option<T>, Error>
    where
        P: Params,
        F: FnOnce(&Row<'_>) -> Result<T, Error>;

    fn vector<T, P, F>(&self, sql: &str, params: P, f: F) -> Result<Vec<T>, Error>
    where
        P: Params,
        F: FnMut(&Row<'_>) -> Result<T, Error>;
}

impl ConnectionExt for Connection {
    fn one_or_none<T, P, F>(&self, sql: &str, params: P, f: F) -> Result<Option<T>, Error>
    where
        P: Params,
        F: FnOnce(&Row<'_>) -> Result<T, Error>,
    {
        self.prepare_cached(sql)?.one_or_none(params, f)
    }

    fn optional<T, P, F>(&self, sql: &str, params: P, f: F) -> Result<Option<T>, Error>
    where
        P: Params,
        F: FnOnce(&Row<'_>) -> Result<T, Error>,
    {
        self.prepare_cached(sql)?.optional(params, f)
    }

    fn vector<T, P, F>(&self, sql: &str, params: P, f: F) -> Result<Vec<T>, Error>
    where
        P: Params,
        F: FnMut(&Row<'_>) -> Result<T, Error>,
    {
        self.prepare_cached(sql)?.vector(params, f)
    }
}

pub trait StatementExt {
    fn one_or_none<T, P, F>(&mut self, params: P, f: F) -> Result<Option<T>, Error>
    where
        P: Params,
        F: FnOnce(&Row<'_>) -> Result<T, Error>;

    fn optional<T, P, F>(&mut self, params: P, f: F) -> Result<Option<T>, Error>
    where
        P: Params,
        F: FnOnce(&Row<'_>) -> Result<T, Error>;

    fn vector<T, P, F>(&mut self, params: P, f: F) -> Result<Vec<T>, Error>
    where
        P: Params,
        F: FnMut(&Row<'_>) -> Result<T, Error>;
}

impl StatementExt for Statement<'_> {
    fn one_or_none<T, P, F>(&mut self, params: P, f: F) -> Result<Option<T>, Error>
    where
        P: Params,
        F: FnOnce(&Row<'_>) -> Result<T, Error>,
    {
        self.query_one(params, f).optional()
    }

    fn optional<T, P, F>(&mut self, params: P, f: F) -> Result<Option<T>, Error>
    where
        P: Params,
        F: FnOnce(&Row<'_>) -> Result<T, Error>,
    {
        self.query_row(params, f).optional()
    }

    fn vector<T, P, F>(&mut self, params: P, f: F) -> Result<Vec<T>, Error>
    where
        P: Params,
        F: FnMut(&Row<'_>) -> Result<T, Error>,
    {
        self.query_map(params, f)?.try_collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn new_mock() -> Result<Connection, Error> {
        let conn = Connection::open_in_memory()?;
        conn.execute(
            "CREATE TABLE testdata (x INTEGER PRIMARY KEY, y TEXT NOT NULL)",
            (),
        )?;
        conn.execute("INSERT INTO testdata (x, y) VALUES (?1, ?2)", (&1, "foo"))?;
        conn.execute("INSERT INTO testdata (x, y) VALUES (?1, ?2)", (&2, "bar"))?;
        Ok(conn)
    }

    fn y(row: &Row) -> Result<String, Error> {
        row.get(0)
    }

    #[test]
    fn one_or_none() {
        let conn = new_mock().unwrap();

        assert_eq!(
            conn.one_or_none("SELECT y FROM testdata WHERE x = ?1", [1], y),
            Ok(Some("foo".to_string())),
        );
        assert_eq!(
            conn.one_or_none("SELECT y FROM testdata WHERE x = ?1", [2], y),
            Ok(Some("bar".to_string())),
        );
        assert_eq!(
            conn.one_or_none("SELECT y FROM testdata WHERE x = ?1", [3], y),
            Ok(None),
        );

        assert_eq!(
            conn.one_or_none("SELECT y FROM testdata", [], y),
            Err(Error::QueryReturnedMoreThanOneRow),
        );
    }

    #[test]
    fn optional() {
        let conn = new_mock().unwrap();

        assert_eq!(
            conn.optional("SELECT y FROM testdata WHERE x = ?1", [1], y),
            Ok(Some("foo".to_string())),
        );
        assert_eq!(
            conn.optional("SELECT y FROM testdata WHERE x = ?1", [2], y),
            Ok(Some("bar".to_string())),
        );
        assert_eq!(
            conn.optional("SELECT y FROM testdata WHERE x = ?1", [3], y),
            Ok(None),
        );

        assert_eq!(
            conn.optional("SELECT y FROM testdata", [], y),
            Ok(Some("foo".to_string())),
        );
    }

    #[test]
    fn vector() {
        let conn = new_mock().unwrap();

        assert_eq!(
            conn.vector("SELECT y FROM testdata WHERE x = ?1", [1], y),
            Ok(vec!["foo".to_string()]),
        );
        assert_eq!(
            conn.vector("SELECT y FROM testdata WHERE x = ?1", [2], y),
            Ok(vec!["bar".to_string()]),
        );
        assert_eq!(
            conn.vector("SELECT y FROM testdata WHERE x = ?1", [3], y),
            Ok(vec![]),
        );

        assert_eq!(
            conn.vector("SELECT y FROM testdata", [], y),
            Ok(vec!["foo".to_string(), "bar".to_string()]),
        );
    }
}
