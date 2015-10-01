"""Automate SQL table creation."""

__all__ = [
    'make_table',
    'iter_columns',
]

import logging

from sqlalchemy import (
    Table,
    Column,
    ForeignKey,
    Integer,
)

from garage import preconds
from garage.specs import sql


LOG = logging.getLogger(__name__)


def make_table(model, metadata, spec_attr=sql.SPEC_ATTR_NAME):
    columns = list(iter_columns(model, spec_attr))
    preconds.check_state(columns)
    for column in columns:
        if column.primary_key:
            break
    else:
        LOG.debug('generate primary key for model %s', model.name)
        columns.insert(0, Column('_id', Integer, primary_key=True))
    return Table(model.attrs[spec_attr].name, metadata, *columns)


def iter_columns(model, spec_attr=sql.SPEC_ATTR_NAME):
    for field in model:
        column_spec = field.attrs.get(spec_attr)
        if column_spec is None:
            LOG.debug('ignore %s.%s when making columns',
                      model.name, field.name)
        elif column_spec.foreign_spec:
            if column_spec.type is not None:
                LOG.warning('ignore column type of %s.%s',
                            model.name, field.name)
            foreign_spec = column_spec.foreign_spec
            if foreign_spec.cardinality is sql.ONE:
                yield make_foreign_key_column(
                    field.name, foreign_spec, spec_attr)
        else:
            preconds.check_state(column_spec.type is not None)
            attrs = column_spec.extra_attrs.copy()
            if column_spec.is_primary_key:
                attrs['primary_key'] = True
            yield Column(field.name, column_spec.type, **attrs)


def make_foreign_key_column(column_name, foreign_spec, spec_attr):
    foreign_field = get_foreign_field(foreign_spec, spec_attr)
    foreign_column_spec = foreign_field.attrs[spec_attr]
    preconds.check_state(foreign_column_spec.type is not None)

    model_name = foreign_spec.model.attrs[spec_attr].name
    foreign_key = ForeignKey('%s.%s' % (model_name, foreign_field.name))

    return Column(column_name, foreign_column_spec.type, foreign_key)


def get_foreign_field(foreign_spec, spec_attr):
    if foreign_spec.field_name:
        return foreign_spec.model.fields[foreign_spec.field_name]
    # If foreign field is not specified, use primary key (in this case
    # you should have only one primary key so that it is unambiguous).
    primary_keys = list_primary_keys(foreign_spec.model, spec_attr)
    preconds.check_state(len(primary_keys) == 1)
    return primary_keys[0]


def list_primary_keys(model, spec_attr):
    return list(iter_primary_keys(model, spec_attr))


def iter_primary_keys(model, spec_attr):
    for field in model:
        column_spec = field.attrs.get(spec_attr)
        if column_spec is not None and column_spec.is_primary_key:
            yield field
