"""Helpers for CRUD operations."""

__all__ = [
    'make_insert',
]

from garage import models
from garage.specs import sql


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
