__all__ = [
    'add_if_not_exists_clause',
    'ensure_only_one_row',
    'insert_or_ignore',
]

from garage.assertions import ASSERT

from sqlalchemy.schema import CreateIndex


def add_if_not_exists_clause(index, engine):
    # `sqlalchemy.Index.create()` does not take `checkfirst` for reasons
    # that I am unaware of, and here is a hack for sidestep that.
    stmt = str(CreateIndex(index).compile(engine))
    stmt = stmt.replace('CREATE INDEX', 'CREATE INDEX IF NOT EXISTS', 1)
    ASSERT('IF NOT EXISTS' in stmt, 'stmt=%s', stmt)
    return stmt


def ensure_only_one_row(rows):
    row = rows.fetchone()
    if row is None or rows.fetchone() is not None:
        raise KeyError
    return row


def insert_or_ignore(conn, table, values):
    conn.execute(table.insert().prefix_with('OR IGNORE'), values)
