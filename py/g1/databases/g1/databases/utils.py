__all__ = [
    'add_if_not_exists_clause',
]

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
