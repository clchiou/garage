"""Automate SQL table creation."""

__all__ = [
    'is_not_foreign',
    'make_table',
    'make_junction_table',
    'iter_columns',
    'iter_junction_columns',
]

import logging

from sqlalchemy import (
    Table,
    Column,
    Boolean,
    Float,
    Integer,
    String,
    ForeignKey,
    UniqueConstraint,
)

from garage import asserts
from garage.sql.specs import SPEC_ATTR_NAME


LOG = logging.getLogger(__name__)


def is_not_foreign(field, *, spec_attr=SPEC_ATTR_NAME):
    """True if field maps to a column that is not a foreign key."""
    column_spec = field.attrs.get(spec_attr)
    return column_spec and not column_spec.foreign_key_spec


def make_table(model, metadata, *, spec_attr=SPEC_ATTR_NAME):
    columns = list(iter_columns(model, spec_attr=spec_attr))
    asserts.postcond(columns)
    columns.extend(iter_constraints(model.attrs[spec_attr].constraints))
    return Table(model.attrs[spec_attr].name, metadata, *columns)


def iter_columns(model, *, spec_attr=SPEC_ATTR_NAME):
    column_attrs = model.attrs[spec_attr].column_attrs
    for field in model:
        column_spec = field.attrs.get(spec_attr)
        if column_spec is None:
            LOG.debug('ignore %s.%s when making columns',
                      model.name, field.name)
            continue
        yield _make_column(
            model.name, field.name, column_spec, column_attrs, spec_attr)
    for column_name, column_spec in model.attrs[spec_attr].extra_columns:
        yield _make_column(
            model.name, column_name, column_spec, column_attrs, spec_attr)


def iter_constraints(constraint_specs):
    for constraint_spec in constraint_specs:
        if constraint_spec.constraint == 'unique':
            yield UniqueConstraint(*constraint_spec.field_names)
        else:
            raise ValueError('could not recognize constraint %r' %
                             constraint_spec.constraint)


def make_junction_table(
        models, table_name, metadata, *, spec_attr=SPEC_ATTR_NAME):
    columns = list(iter_junction_columns(models, spec_attr=spec_attr))
    asserts.postcond(columns)
    return Table(table_name, metadata, *columns)


def iter_junction_columns(models, *, spec_attr=SPEC_ATTR_NAME):
    for model in models:
        table_spec = model.attrs[spec_attr]
        model_name = table_spec.short_name or table_spec.name
        pairs = _iter_primary_key_pairs(model, spec_attr)
        for column_name, column_type in pairs:
            asserts.precond(column_type is not None)
            yield Column(
                '%s_%s' % (model_name, column_name),
                _convert_type(column_type),
                ForeignKey('%s.%s' % (table_spec.name, column_name)),
                primary_key=True,
            )


def _make_column(model_name, field_name, column_spec, column_attrs, spec_attr):
    if column_spec.foreign_key_spec:
        if column_spec.type is not None:
            LOG.warning('ignore column type of %s.%s', model_name, field_name)
        return _make_foreign_key_column(
            field_name, column_spec.foreign_key_spec, spec_attr)
    else:
        asserts.precond(column_spec.type is not None)
        attrs = column_attrs.copy()
        attrs.update(column_spec.extra_attrs)
        if column_spec.is_primary_key:
            attrs['primary_key'] = True
        return Column(field_name, _convert_type(column_spec.type), **attrs)


def _make_foreign_key_column(column_name, foreign_key_spec, spec_attr):
    foreign_column_name, foreign_column_type = _get_foreign_key_pair(
        foreign_key_spec, spec_attr)
    asserts.precond(foreign_column_type is not None)
    return Column(
        column_name,
        _convert_type(foreign_column_type),
        ForeignKey('%s.%s' % (
            foreign_key_spec.model.attrs[spec_attr].name,
            foreign_column_name,
        )),
    )


def _get_foreign_key_pair(foreign_key_spec, spec_attr):
    if foreign_key_spec.field:
        foreign_column_spec = foreign_key_spec.field.attrs[spec_attr]
        asserts.precond(foreign_column_spec.type is not None)
        return foreign_key_spec.field.name, foreign_column_spec.type
    # If foreign field is not specified, use primary key (in this case
    # you should have only one primary key so that it is unambiguous).
    primary_key_pairs = list(
        _iter_primary_key_pairs(foreign_key_spec.model, spec_attr))
    asserts.precond(len(primary_key_pairs) == 1)
    return primary_key_pairs[0]


def _iter_primary_key_pairs(model, spec_attr):
    """Yield (column_name, column_type) of primary key columns."""
    for field in model:
        column_spec = field.attrs.get(spec_attr)
        if column_spec is not None and column_spec.is_primary_key:
            asserts.precond(column_spec.type is not None)
            yield field.name, column_spec.type
    for column_name, column_spec in model.attrs[spec_attr].extra_columns:
        if column_spec.is_primary_key:
            yield column_name, column_spec.type


def _convert_type(type_):
    return {
        bool: Boolean,
        float: Float,
        int: Integer,
        str: String,
    }.get(type_, type_)
