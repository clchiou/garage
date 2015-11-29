"""Use conventions for making SQL tables."""

__all__ = [
    'iter_tables',
    'make_table_name',
]

from garage.sql.tables import (
    make_junction_table,
    make_table,
)

from . import make_junction_table_short_name


def iter_tables(context, models, junction_models, metadata):
    for model in models:
        yield model.a.sql.short_name, make_table(model, metadata)
    for junction_model in junction_models:
        short_name = make_junction_table_short_name(junction_model)
        table = make_junction_table(
            junction_model, context[short_name], metadata)
        yield short_name, table


def make_table_name(short_name, prefix, suffix):
    return '%s%s%s%s%s' % (
        prefix,
        '_' if prefix else '',
        short_name,
        '_' if suffix else '',
        suffix,
    )
