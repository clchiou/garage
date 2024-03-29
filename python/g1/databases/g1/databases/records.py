"""SQLite-based record storage.

It supports two kinds of data model:

* Keyed, which acts like a tuple-to-tuple dict.
* Keyless, which acts like a list of tuples.

We believe that these data models should be quite common, and so we make
a module (this module) to support them.
"""

__all__ = [
    'Records',
    'RecordsSchema',
]

import collections.abc

from sqlalchemy import (
    Column,
    Index,
    LargeBinary,
    MetaData,
    Table,
    and_,
    func,
    literal,
    select,
)

from g1.bases.assertions import ASSERT

from . import sqlite
from . import utils


class RecordsSchema:

    def __init__(
        self,
        table_name,
        key_column_names_and_types=(),
        value_column_names_and_types=(('data', LargeBinary), ),
        *,
        metadata=None,
        index_column_names=(),  # This is actually a list of names.
        constraints=(),
    ):
        ASSERT.isdisjoint(
            frozenset(name for name, _ in key_column_names_and_types),
            frozenset(name for name, _ in value_column_names_and_types),
        )
        # We do not support the valueless use case for now.
        ASSERT.not_empty(value_column_names_and_types)
        self.metadata = MetaData() if metadata is None else metadata
        self.table_name = table_name
        self.key_column_names = tuple(
            name for name, _ in key_column_names_and_types
        )
        self.key_columns = tuple(
            Column(*pair, nullable=False, primary_key=True)
            for pair in key_column_names_and_types
        )
        self.value_column_names = tuple(
            name for name, _ in value_column_names_and_types
        )
        self.value_columns = tuple(
            Column(*pair, nullable=False)
            for pair in value_column_names_and_types
        )
        self.index_column_names = index_column_names
        self.table = Table(
            table_name,
            self.metadata,
            *self.key_columns,
            *self.value_columns,
            *constraints,
        )

    def make_indices(self):
        return [
            Index(
                'index_%s__%s' % (self.table_name, '__'.join(names)),
                *map(
                    self.table.columns.__getitem__,  # pylint: disable=no-member
                    names,
                ),
            ) for names in self.index_column_names
        ]

    def is_keyed(self):
        return bool(self.key_column_names)

    def assert_keyed(self):
        ASSERT.true(self.is_keyed(), message='expect keyed schema')

    def assert_keyless(self):
        ASSERT.false(self.is_keyed(), message='expect keyless schema')

    def _maybe_make_query(self, query, make_query):
        if make_query is not None:
            query = make_query(query, self.table.columns)
        return query

    def _by_keys(self, keys):
        ASSERT.equal(len(keys), len(self.key_columns))
        return and_(*(c == k for c, k in zip(self.key_columns, keys)))

    def query_count(self, make_query=None):
        return self._maybe_make_query(
            select([func.count()]).select_from(self.table),
            make_query,
        )

    def query_contains_keys(self, keys):
        return select([literal(True)]).where(self._by_keys(keys)).limit(1)

    def query_keys(self, make_query=None):
        return self._maybe_make_query(
            select(self.key_columns),
            make_query,
        )

    def query_values(self, make_query=None):
        return self._maybe_make_query(
            select(self.value_columns),
            make_query,
        )

    def query_values_by_keys(self, keys):
        return select(self.value_columns).where(self._by_keys(keys))

    def query_items(self, make_query=None):
        return self._maybe_make_query(
            select(self.table.columns),
            make_query,
        )

    def make_upsert_statement(self):
        return sqlite.upsert(self.table)

    def make_insert_statement(self):
        return self.table.insert()  # pylint: disable=no-value-for-parameter

    def make_delete_statement(self, make_query=None):
        return self._maybe_make_query(
            self.table.delete(),  # pylint: disable=no-value-for-parameter
            make_query,
        )

    def make_record(self, keys, values):
        ASSERT.equal(len(keys), len(self.key_columns))
        ASSERT.equal(len(values), len(self.value_columns))
        record = dict(zip(self.key_column_names, keys))
        record.update(zip(self.value_column_names, values))
        return record


class Records(collections.abc.Collection):
    """Collection of optionally-keyed record storage.

    When the storage is keyed, its interface is dict-like, and when it
    is keyless, its interface is list-like.

    Note that since this is a collection type, ``bool(records)`` is
    evaluated to false when ``records`` is empty.  Don't be surprised!
    """

    def __init__(self, conn, schema):
        self._conn = conn
        self._schema = schema

    def create_all(self):
        self._schema.metadata.create_all(self._conn)

    def create_indices(self):
        for index in self._schema.make_indices():
            index.create(self._conn, checkfirst=True)

    def __len__(self):
        # This works in both keyed and keyless schema.
        return self.count()

    def __iter__(self):
        # This works in both keyed and keyless schema.
        if self._schema.is_keyed():
            return self.search_keys()
        else:
            return self.search_values()

    def __contains__(self, keys):
        # Sadly this only works in keyed schema for now.
        self._schema.assert_keyed()
        stmt = self._schema.query_contains_keys(keys)
        return self._conn.execute(stmt).scalar() is not None

    def __getitem__(self, keys):
        # Sadly this only works in keyed schema for now.
        self._schema.assert_keyed()
        values = self.get(keys)
        if values is None:
            raise KeyError(keys)
        return values

    def __setitem__(self, keys, values):
        # Sadly this only works in keyed schema for now.
        self._schema.assert_keyed()
        self._conn.execute(
            self._schema.make_upsert_statement(),
            [self._schema.make_record(keys, values)],
        )

    def count(self, make_query=None):
        # This works in both keyed and keyless schema.
        stmt = self._schema.query_count(make_query)
        return ASSERT.not_none(self._conn.execute(stmt).scalar())

    def keys(self):
        yield from self.search_keys()

    def values(self):
        yield from self.search_values()

    def items(self):
        yield from self.search_items()

    def get(self, keys, default=None):
        self._schema.assert_keyed()
        stmt = self._schema.query_values_by_keys(keys)
        row = self._conn.execute(stmt).one_or_none()
        if row is None:
            return default
        else:
            return tuple(row)

    def search_keys(self, make_query=None):
        self._schema.assert_keyed()
        stmt = self._schema.query_keys(make_query)
        return _iter_rows(self._conn, stmt)

    def search_values(self, make_query=None):
        # This works in both keyed and keyless schema.
        stmt = self._schema.query_values(make_query)
        return _iter_rows(self._conn, stmt)

    def search_items(self, make_query=None):
        self._schema.assert_keyed()
        stmt = self._schema.query_items(make_query)
        with utils.executing(self._conn, stmt) as result:
            for row in result:
                yield (
                    tuple(row[c] for c in self._schema.key_columns),
                    tuple(row[c] for c in self._schema.value_columns),
                )

    def update(self, pairs):
        self._schema.assert_keyed()
        if hasattr(pairs, 'items'):
            pairs = pairs.items()
        self._conn.execute(
            self._schema.make_upsert_statement(),
            [self._schema.make_record(*pair) for pair in pairs],
        )

    def append(self, record):
        self._schema.assert_keyless()
        self._conn.execute(
            self._schema.make_insert_statement(),
            [self._schema.make_record((), record)],
        )

    def extend(self, records):
        self._schema.assert_keyless()
        self._conn.execute(
            self._schema.make_insert_statement(),
            [self._schema.make_record((), record) for record in records],
        )

    def delete(self, make_query=None):
        # This works in both keyed and keyless schema.
        self._conn.execute(self._schema.make_delete_statement(make_query))


def _iter_rows(conn, select_stmt):
    with utils.executing(conn, select_stmt) as result:
        for row in result:
            yield tuple(row)
