"""SQLite-based binary record storage."""

__all__ = [
    'Records',
    'RecordsSchema',
]

import collections.abc
import contextlib

from sqlalchemy import (
    Column,
    Index,
    LargeBinary,
    MetaData,
    Table,
    UniqueConstraint,
    and_,
    func,
    select,
)

from g1.bases import classes
from g1.bases.assertions import ASSERT

from .utils import add_if_not_exists_clause


class RecordsSchema:

    def __init__(
        self,
        table_name,
        key_column_names_and_types=(),
        data_column_name='data',
        *,
        metadata=None,
    ):

        self.metadata = MetaData() if metadata is None else metadata

        self.key_column_names = tuple(n for n, _ in key_column_names_and_types)
        self.key_columns = tuple(
            Column(*pair, nullable=False)
            for pair in key_column_names_and_types
        )

        # Just a sanity check.
        ASSERT.not_in(data_column_name, self.key_column_names)

        self.data_column_name = data_column_name
        self.data_column = \
            Column(data_column_name, LargeBinary, nullable=False)

        self.table = Table(
            table_name,
            self.metadata,
            *self.key_columns,
            self.data_column,
            *self._make_key_constraints(),
        )

    def _make_key_constraints(self):
        if not self.key_column_names:
            return ()
        # There is only one constraint at the moment.
        return (
            UniqueConstraint(
                *self.key_column_names,
                name='unique_%s' % '_'.join(self.key_column_names),
            ),
        )

    def make_indices(self):
        if not self.key_column_names:
            return ()
        # There is only one index at the moment.
        return (
            Index(
                'index_%s' % '_'.join(self.key_column_names),
                *self.key_columns,
            ),
        )


class Records(collections.abc.Collection):
    """Collection of optionally-keyed binary records.

    Overall the interface is dict-like, but on keyless records, methods
    that require keys will raise ``AssertionError`` with a few things
    deviated from dict interface:

    * Records are indexed by a tuple of keys, as defined in the schema.
      This might be confusing when you want to distinguish between a
      tuple of "keys" versus a list of tuple of "keys".

    * The term "value" is renamed to "record", and records are always
      ``bytes``-typed.

    Note that since this is a collection type, ``bool(records)`` is
    evaluated to false when ``records`` is empty.  Don't be surprised!
    """

    def __init__(self, engine, schema):
        self._engine = engine
        self._schema = schema

    def _assert_keyed(self):
        ASSERT.not_empty(self._schema.key_column_names)

    def _assert_keyless(self):
        ASSERT.empty(self._schema.key_column_names)

    def create_all(self):
        self._schema.metadata.create_all(self._engine)

    def create_indices(self):
        with self._engine.connect() as conn:
            for index in self._schema.make_indices():
                conn.execute(add_if_not_exists_clause(index, self._engine))

    @classes.memorizing_property
    def _insert_stmt(self):
        return self._schema.table.insert()

    @classes.memorizing_property
    def _upsert_stmt(self):
        # NOTE: This is SQLite-specific.
        return self._schema.table.insert().prefix_with('OR REPLACE')

    def _prepare_select_stmt(self, select_stmt, make_where_clause):
        if make_where_clause:
            self._assert_keyed()
            select_stmt = select_stmt.where(
                make_where_clause(self._schema.table.columns)
            )
        return select_stmt

    def __len__(self):
        return self.count()

    def __iter__(self):
        yield from self.search_keys()

    def __contains__(self, keys):
        return self.count(lambda _: self._get(keys)) > 0

    def __getitem__(self, keys):
        record = self.get(keys)
        if record is None:
            raise KeyError(keys)
        return record

    def __setitem__(self, keys, record):
        self.insert(keys, record)

    def keys(self):
        yield from self.search_keys()

    def records(self):
        yield from self.search_records()

    def items(self):
        yield from self.search_items()

    def get(self, keys, default=None):
        select_stmt = self._prepare_select_stmt(
            select([self._schema.data_column]),
            lambda _: self._get(keys),
        )
        with self._engine.connect() as conn:
            return conn.execute(select_stmt).scalar() or default

    def _get(self, keys):
        if not isinstance(keys, tuple):
            keys = (keys, )
        ASSERT.equal(len(keys), len(self._schema.key_columns))
        return and_(
            *(
                key_column == key
                for key_column, key in zip(self._schema.key_columns, keys)
            )
        )

    def count(self, make_where_clause=None):
        select_stmt = self._prepare_select_stmt(
            select([func.count()]).select_from(self._schema.table),
            make_where_clause,
        )
        with self._engine.connect() as conn:
            return ASSERT.not_none(conn.execute(select_stmt).scalar())

    def search_keys(self, make_where_clause=None):
        self._assert_keyed()
        select_stmt = self._prepare_select_stmt(
            select(self._schema.key_columns),
            make_where_clause,
        )
        with self._engine.connect() as conn:
            with contextlib.closing(conn.execute(select_stmt)) as result:
                yield from result

    def search_records(self, make_where_clause=None):
        select_stmt = self._prepare_select_stmt(
            select([self._schema.data_column]),
            make_where_clause,
        )
        with self._engine.connect() as conn:
            with contextlib.closing(conn.execute(select_stmt)) as result:
                for row in result:
                    yield row[0]

    def search_items(self, make_where_clause=None):
        self._assert_keyed()
        select_stmt = self._prepare_select_stmt(
            select(self._schema.table.columns),
            make_where_clause,
        )
        with self._engine.connect() as conn:
            with contextlib.closing(conn.execute(select_stmt)) as result:
                for row in result:
                    yield (
                        tuple(row[c] for c in self._schema.key_columns),
                        row[self._schema.data_column],
                    )

    def insert(self, keys, record):
        """Insert one record; only valid for keyed ``Records``."""
        self._assert_keyed()
        self._upsert([self._make_keyed_values(keys, record)])

    def update(self, keys_records):
        """Insert many records; only valid for keyed ``Records``."""
        self._assert_keyed()
        if hasattr(keys_records, 'items'):
            keys_records = keys_records.items()
        self._upsert([self._make_keyed_values(*pair) for pair in keys_records])

    def _upsert(self, values_list):
        with self._engine.connect() as conn:
            conn.execute(self._upsert_stmt, values_list)

    def _make_keyed_values(self, keys, record):
        ASSERT.isinstance(record, bytes)

        if not isinstance(keys, tuple):
            keys = (keys, )
        ASSERT.equal(len(keys), len(self._schema.key_column_names))

        values = dict(zip(self._schema.key_column_names, keys))
        values[self._schema.data_column_name] = record

        return values

    def append(self, record):
        """Append one record; only valid for keyless ``Records``."""
        self._assert_keyless()
        self._insert([self._make_keyless_values(record)])

    def extend(self, records):
        """Append many records; only valid for keyless ``Records``."""
        self._assert_keyless()
        self._insert(list(map(self._make_keyless_values, records)))

    def _insert(self, values_list):
        with self._engine.connect() as conn:
            conn.execute(self._insert_stmt, values_list)

    def _make_keyless_values(self, record):
        ASSERT.isinstance(record, bytes)
        return {self._schema.data_column_name: record}
