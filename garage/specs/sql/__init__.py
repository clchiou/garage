"""Specify and automate some SQL operations."""

__all__ = [
    'ONE',
    'MANY',
    'table_spec',
    'column_spec',
    'foreign_spec',
]

import enum

from garage import models
from garage.specs import base


SPEC_ATTR_NAME = 'sql'


class Cardinality(enum.Enum):
    ONE = 'ONE'
    MANY = 'MANY'


ONE = Cardinality.ONE
MANY = Cardinality.MANY


TABLE_SPEC_MODEL = (
    models.Model('TABLE_SPEC_MODEL')
    .field('name', doc="""SQL table name.""")
)


COLUMN_SPEC_MODEL = (
    models.Model('COLUMN_SPEC_MODEL')
    .field('is_primary_key', doc="""Indicate this column is a primary key.""")
    .field('is_natural_key', doc="""Indicate this column is a natural key.""")
    .field('foreign_spec', doc="""Specify foreign key relationship.""")
    .field('type', doc="""SQL storage type.""")
    .field('extra_attrs', doc="""Additional column attributes.""")
)


COLUMN_SPEC_DEFAULTS = {
    'is_primary_key': False,
    'is_natural_key': False,
    'foreign_spec': None,
    'type': None,
    'extra_attrs': {},
}


FOREIGN_SPEC_MODEL = (
    models.Model('FOREIGN_SPEC_MODEL')
    .field('model', doc="""Refer to this foreign model.""")
    .field('field_name', doc="""Refer to this column of the foreign model.""")
    .field('cardinality', doc="""The cardinality of this relationship.""")
)


FOREIGN_SPEC_DEFAULTS = {
    'field_name': None,
}


TableSpec = base.make_namedtuple(TABLE_SPEC_MODEL, 'TableSpec')
ColumnSpec = base.make_namedtuple(COLUMN_SPEC_MODEL, 'ColumnSpec')
ForeignSpec = base.make_namedtuple(FOREIGN_SPEC_MODEL, 'ForeignSpec')


def table_spec(**kwargs):
    return TableSpec(**kwargs)


def column_spec(**kwargs):
    data = COLUMN_SPEC_DEFAULTS.copy()
    data.update(kwargs)
    return ColumnSpec(**data)


def foreign_spec(**kwargs):
    data = FOREIGN_SPEC_DEFAULTS.copy()
    data.update(kwargs)
    return ForeignSpec(**data)
