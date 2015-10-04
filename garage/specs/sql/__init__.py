"""Specify and automate some SQL operations."""

__all__ = [
    'table_spec',
    'column_spec',
    'foreign_key_spec',
]

from garage import models
from garage.functools import with_defaults
from garage.specs import base


SPEC_ATTR_NAME = 'sql'


TABLE_SPEC_MODEL = (
    models.Model('TABLE_SPEC_MODEL')
    .field('name', doc="""SQL table name.""")
    .field('short_name', doc="""Shorter name for junction tables.""")
    .field('column_attrs', doc="""Default column attributes""")
    .field('extra_columns', doc="""More SQL columns""")
)


table_spec = with_defaults(
    base.make_as_namespace(TABLE_SPEC_MODEL),
    {
        'short_name': None,
        'column_attrs': {},
        'extra_columns': (),
    },
)


COLUMN_SPEC_MODEL = (
    models.Model('COLUMN_SPEC_MODEL')
    .field('is_primary_key', doc="""Indicate this column is a primary key.""")
    .field('foreign_key_spec', doc="""Specify foreign key relationship.""")
    .field('type', doc="""SQL storage type.""")
    .field('extra_attrs', doc="""Additional column attributes.""")
)


column_spec = with_defaults(
    base.make_as_namespace(COLUMN_SPEC_MODEL),
    {
        'is_primary_key': False,
        'foreign_key_spec': None,
        'type': None,
        'extra_attrs': {},
    },
)


FOREIGN_KEY_SPEC_MODEL = (
    models.Model('FOREIGN_KEY_SPEC_MODEL')
    .field('model', doc="""Refer to this foreign model.""")
    .field('field_name', doc="""Refer to this column of the foreign model.""")
)


foreign_key_spec = with_defaults(
    base.make_as_namespace(FOREIGN_KEY_SPEC_MODEL),
    {
        'field_name': None,
    },
)
