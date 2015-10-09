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
from collections import (
    Mapping,
    OrderedDict,
    Sequence,
    Set,
)
from contextlib import closing
from datetime import datetime

from sqlalchemy import select

from garage import asserts
from garage import models
from garage.sql.specs import SPEC_ATTR_NAME
from garage.sql.tables import is_not_foreign


LOG = logging.getLogger(__name__)


# ISO 8601 date and time format (with time zone designator).
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%f%z'
DATETIME_FORMAT_WO_TIMEZONE = '%Y-%m-%dT%H:%M:%S.%f'


def make_select_by(key_column, *value_columns):

    columns = list(value_columns)
    columns.insert(0, key_column)

    def select_by(conn, keys):
        query = select(columns).where(key_column.in_(keys))
        with closing(conn.execute(query)) as rows:
            yield from rows

    return select_by


def make_insert(model, *, spec_attr=SPEC_ATTR_NAME):

    as_dict = models.make_as_dict(
        field for field in model if is_not_foreign(field, spec_attr=spec_attr))

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


_ELEMENT_TYPES = frozenset((int, float, str, datetime))


def serialize(obj):
    if isinstance(obj, Sequence) and not isinstance(obj, str):
        data = ['L']
        for element in obj:
            data.extend(_serialize(element))
        return json.dumps(data)
    elif isinstance(obj, Set):
        data = ['S']
        for element in obj:
            data.extend(_serialize(element))
        return json.dumps(data)
    elif isinstance(obj, Mapping):
        data = ['M']
        for key, value in obj.items():
            data.extend(_serialize(key))
            data.extend(_serialize(value))
        return json.dumps(data)
    else:
        return json.dumps(_serialize(obj))


def _serialize(value):
    typ = type(value)
    asserts.precond(
        typ in _ELEMENT_TYPES, 'cannot serialize %r of type %r', value, typ)
    return [
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
    ]


def deserialize(json_str):
    packed_obj = json.loads(json_str)
    asserts.precond(packed_obj)
    if packed_obj[0] == 'L':
        return tuple(
            _deserialize(packed_obj[i:i+2])
            for i in range(1, len(packed_obj), 2)
        )
    elif packed_obj[0] == 'S':
        return frozenset(
            _deserialize(packed_obj[i:i+2])
            for i in range(1, len(packed_obj), 2)
        )
    elif packed_obj[0] == 'M':
        return OrderedDict(
            (
                _deserialize(packed_obj[i:i+2]),
                _deserialize(packed_obj[i+2:i+4]),
            )
            for i in range(1, len(packed_obj), 4)
        )
    else:
        asserts.precond(len(packed_obj) == 2)
        return _deserialize(packed_obj)


def _deserialize(packed_value):
    asserts.precond(packed_value[0] in ('i', 'f', 's', 'dt'))
    return {
        'i': int,
        'f': float,
        's': str,
        'dt': _parse_datetime,
    }[packed_value[0]](packed_value[1])


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
