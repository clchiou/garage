"""Automate SQL table creation."""

__all__ = [
    'make_table',
    'make_junction_table',
    'iter_columns',
    'iter_junction_columns',
]

import logging

from sqlalchemy import (
    Table,
    Column,
    ForeignKey,
)

from garage import preconds
from garage.specs import sql


LOG = logging.getLogger(__name__)


def make_table(model, metadata, *, spec_attr=sql.SPEC_ATTR_NAME):
    columns = list(iter_columns(model, spec_attr=spec_attr))
    preconds.check_state(columns)
    return Table(model.attrs[spec_attr].name, metadata, *columns)


def iter_columns(model, *, spec_attr=sql.SPEC_ATTR_NAME):
    table_spec = model.attrs[spec_attr]
    for field in model:
        column_spec = field.attrs.get(spec_attr)
        if column_spec is None:
            LOG.debug('ignore %s.%s when making columns',
                      model.name, field.name)
        elif column_spec.foreign_key_spec:
            if column_spec.type is not None:
                LOG.warning('ignore column type of %s.%s',
                            model.name, field.name)
            yield _make_foreign_key_column(
                field.name, column_spec.foreign_key_spec, spec_attr)
        else:
            preconds.check_state(column_spec.type is not None)
            attrs = table_spec.column_attrs.copy()
            attrs.update(column_spec.extra_attrs)
            if column_spec.is_primary_key:
                attrs['primary_key'] = True
            yield Column(field.name, column_spec.type, **attrs)
    # And don't forget extra_columns.
    yield from model.attrs[spec_attr].extra_columns


def make_junction_table(
        models, table_name, metadata, *, spec_attr=sql.SPEC_ATTR_NAME):
    columns = list(iter_junction_columns(models, spec_attr=spec_attr))
    preconds.check_state(columns)
    return Table(table_name, metadata, *columns)


def iter_junction_columns(models, *, spec_attr=sql.SPEC_ATTR_NAME):
    for model in models:
        table_spec = model.attrs[spec_attr]
        model_name = table_spec.short_name or table_spec.name
        pairs = _iter_primary_key_pairs(model, spec_attr)
        for column_name, column_type in pairs:
            preconds.check_state(column_type is not None)
            yield Column(
                '%s_%s' % (model_name, column_name),
                column_type,
                ForeignKey('%s.%s' % (table_spec.name, column_name)),
                primary_key=True,
            )


def _make_foreign_key_column(column_name, foreign_key_spec, spec_attr):
    foreign_column_name, foreign_column_type = _get_foreign_key_pair(
        foreign_key_spec, spec_attr)
    preconds.check_state(foreign_column_type is not None)
    return Column(
        column_name,
        foreign_column_type,
        ForeignKey('%s.%s' % (
            foreign_key_spec.model.attrs[spec_attr].name,
            foreign_column_name,
        )),
    )


def _get_foreign_key_pair(foreign_key_spec, spec_attr):
    if foreign_key_spec.field:
        foreign_column_spec = foreign_key_spec.field.attrs[spec_attr]
        preconds.check_state(foreign_column_spec.type is not None)
        return foreign_key_spec.field.name, foreign_column_spec.type
    # If foreign field is not specified, use primary key (in this case
    # you should have only one primary key so that it is unambiguous).
    primary_key_pairs = list(
        _iter_primary_key_pairs(foreign_key_spec.model, spec_attr))
    preconds.check_state(len(primary_key_pairs) == 1)
    return primary_key_pairs[0]


def _iter_primary_key_pairs(model, spec_attr):
    """Yield (column_name, column_type) of primary key columns."""
    for field in model:
        column_spec = field.attrs.get(spec_attr)
        if column_spec is not None and column_spec.is_primary_key:
            preconds.check_state(column_spec.type is not None)
            yield field.name, column_spec.type
    for column in model.attrs[spec_attr].extra_columns:
        if column.primary_key:
            yield column.name, column.type
