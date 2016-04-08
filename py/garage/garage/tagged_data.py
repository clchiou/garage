"""Simple tagged data serialization format on top of JSON that handles
some native Python types like `set` and `datatime` better than plain
JSON.
"""

__all__ = [
    'dumps',
    'loads',
]

import json
from collections import (
    Mapping,
    OrderedDict,
    Sequence,
    Set,
)
from datetime import datetime

from garage import asserts
from garage.datetimes import format_iso8601, parse_iso8601


_ELEMENT_TYPES = frozenset((int, float, str, datetime))


def dumps(obj):
    return json.dumps(_dump(obj))


def _dump(obj):
    if isinstance(obj, Sequence) and not isinstance(obj, str):
        data = ['L']
        data.extend(map(_dump, obj))
        return data
    elif isinstance(obj, Set):
        data = ['S']
        data.extend(map(_dump, obj))
        return data
    elif isinstance(obj, Mapping):
        data = ['M']
        for key, value in obj.items():
            data.append(_dump(key))
            data.append(_dump(value))
        return data
    else:
        return _dump_element(obj)


def _dump_element(value):
    typ = type(value)
    asserts.precond(
        typ in _ELEMENT_TYPES, 'cannot dump %r of type %r', value, typ)
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
            datetime: format_iso8601,
        }[typ](value),
    ]


def loads(json_str):
    return _load(json.loads(json_str))


def _load(packed_obj):
    asserts.precond(packed_obj)
    if packed_obj[0] == 'L':
        return tuple(map(_load, packed_obj[1:]))
    elif packed_obj[0] == 'S':
        return frozenset(map(_load, packed_obj[1:]))
    elif packed_obj[0] == 'M':
        return OrderedDict((_load(packed_obj[i]), _load(packed_obj[i+1]))
                           for i in range(1, len(packed_obj), 2))
    else:
        return _load_element(packed_obj)


def _load_element(packed_value):
    asserts.precond(len(packed_value) == 2)
    asserts.precond(packed_value[0] in ('i', 'f', 's', 'dt'))
    return {
        'i': int,
        'f': float,
        's': str,
        'dt': parse_iso8601,
    }[packed_value[0]](packed_value[1])
