"""Helpers for CRUD operations."""

__all__ = [
    'make_select_by',
    'make_insert',
]

from contextlib import closing

from sqlalchemy import select, tuple_

from garage import models
from garage.specs import sql


def make_select_by(key_column, *value_columns):

    columns = list(value_columns)
    columns.insert(0, key_column)

    def select_by(conn, keys):
        key_tuples = [(key,) for key in keys]
        query = select(columns).where(tuple_(key_column).in_(key_tuples))
        with closing(conn.execute(query)) as rows:
            yield from rows

    return select_by


def make_insert(model, *, spec_attr=sql.SPEC_ATTR_NAME):

    def is_mapped_to_column(field):
        # Foreign keys are handled separately and thus excluded.
        column_spec = field.attrs.get(spec_attr)
        return column_spec and not column_spec.foreign_key_spec

    as_dict = models.make_as_dict(filter(is_mapped_to_column, model))

    def combine(data, more_data):
        if more_data:
            data.update(more_data)
        return data

    def insert_objs_extras(conn, table, objs_extras):
        values = [combine(as_dict(obj), extra) for obj, extra in objs_extras]
        insert(conn, table, values)

    return insert_objs_extras


def insert(conn, table, values):
    conn.execute(table.insert().prefix_with('OR IGNORE'), values)
