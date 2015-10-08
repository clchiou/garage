"""Helpers for CRUD operations."""

__all__ = [
    'make_select_by',
    'make_insert',
    'serialize',
    'deserialize',
    'as_int',
    'as_float',
    'as_str',
]

import json
import logging
from contextlib import closing
from datetime import datetime

from sqlalchemy import select, tuple_

from garage import models
from garage import preconds
from garage.specs import sql


LOG = logging.getLogger(__name__)


# ISO 8601 date and time format (with time zone designator).
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%f%z'
DATETIME_FORMAT_WO_TIMEZONE = '%Y-%m-%dT%H:%M:%S.%f'


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


_TYPES = frozenset((int, float, str, datetime))


def serialize(value):
    typ = type(value)
    preconds.check_argument(typ in _TYPES)
    return json.dumps([
        {
            int: 'i',
            float: 'f',
            str: 's',
            datetime: 'dt',
        }[typ],
        {
            int: str,
            float: str,
            str: str,
            datetime: lambda dt: dt.strftime(DATETIME_FORMAT),
        }[typ](value),
    ])


def deserialize(value):
    pair = json.loads(value)
    preconds.check_argument(
        len(pair) == 2 and pair[0] in ('i', 'f', 's', 'dt'))
    return {
        'i': int,
        'f': float,
        's': str,
        'dt': _parse_datetime,
    }[pair[0]](pair[1])


def _parse_datetime(dt_str):
    for dt_format in (DATETIME_FORMAT, DATETIME_FORMAT_WO_TIMEZONE):
        try:
            return datetime.strptime(dt_str, dt_format)
        except ValueError:
            LOG.debug(
                'cannot parse %r using %r', dt_str, dt_format, exc_info=True)
    raise ValueError('cannot parse %r using ISO-8601 format', dt_str)


def as_int(value):
    return value if isinstance(value, int) else None


def as_float(value):
    if isinstance(value, float):
        return value
    elif isinstance(value, datetime):
        return value.timestamp()
    else:
        return None


def as_str(value):
    if isinstance(value, str):
        return value
    elif isinstance(value, datetime):
        return value.strftime(DATETIME_FORMAT)
    else:
        return None
