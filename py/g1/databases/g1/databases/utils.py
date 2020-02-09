__all__ = [
    'add_if_not_exists_clause',
    'executing',
    'one_or_none',
]

import contextlib

from sqlalchemy.schema import CreateIndex

from g1.bases.assertions import ASSERT


def add_if_not_exists_clause(index, engine):
    """Add "IF NOT EXISTS" clause to create index statement.

    I don't know why but ``sqlalchemy.Index.create()`` does not take a
    ``checkfirst`` argument like the rest of others.
    """
    stmt = str(CreateIndex(index).compile(engine))
    stmt = stmt.replace('CREATE INDEX', 'CREATE INDEX IF NOT EXISTS', 1)
    ASSERT.in_('IF NOT EXISTS', stmt)
    return stmt


@contextlib.contextmanager
def executing(engine, statement):
    with engine.connect() as conn:
        result = conn.execute(statement)
        try:
            yield result
        finally:
            result.close()


# I don't know why but SQLAlchemy only make this available in ORM, not
# in core.
def one_or_none(engine, statement):
    with executing(engine, statement) as result:
        row = result.fetchone()
        ASSERT.none(result.fetchone())
        return row
