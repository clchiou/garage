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


_ELEMENT_TYPES = frozenset((int, float, str, datetime, type(None)))


def dumps(obj, more_element_types=None):
    return json.dumps(_dump(obj, more_element_types or {}))


def _dump(obj, more_element_types):
    if isinstance(obj, Sequence) and not isinstance(obj, str):
        data = ['L']
        data.extend(_dump(item, more_element_types) for item in obj)
        return data
    elif isinstance(obj, Set):
        data = ['S']
        data.extend(_dump(item, more_element_types) for item in obj)
        return data
    elif isinstance(obj, Mapping):
        data = ['M']
        for key, value in obj.items():
            data.append(_dump(key, more_element_types))
            data.append(_dump(value, more_element_types))
        return data
    else:
        return _dump_element(obj, more_element_types)


def _dump_element(value, more_element_types):
    typ = type(value)
    if typ in _ELEMENT_TYPES:
        return [
            {
                int: 'i',
                float: 'f',
                str: 's',
                datetime: 'dt',
                type(None): 'n',
            }[typ],
            {
                int: str,
                float: str,
                str: str,
                datetime: format_iso8601,
                type(None): lambda _: None,
            }[typ](value),
        ]
    elif typ in more_element_types:
        dumper = more_element_types[typ]
        return ['x/%s' % typ.__name__, dumper(value)]
    raise ValueError('cannot dump %r of type %r' % (value, typ))


def loads(json_str, more_element_types=None):
    if more_element_types is not None:
        more_element_types = {
            ('x/%s' % typ.__name__): loader
            for typ, loader in more_element_types.items()
        }
    else:
        more_element_types = {}
    return _load(json.loads(json_str), more_element_types)


def _load(packed_obj, more_element_types):
    asserts.true(packed_obj)
    if packed_obj[0] == 'L':
        return tuple(
            _load(item, more_element_types)
            for item in packed_obj[1:]
        )
    elif packed_obj[0] == 'S':
        return frozenset(
            _load(item, more_element_types)
            for item in packed_obj[1:]
        )
    elif packed_obj[0] == 'M':
        return OrderedDict(
            (_load(packed_obj[i], more_element_types),
             _load(packed_obj[i+1], more_element_types))
            for i in range(1, len(packed_obj), 2)
        )
    else:
        return _load_element(packed_obj, more_element_types)


def _load_element(packed_value, more_element_types):
    asserts.equal(len(packed_value), 2)
    loader_maps = [
        {
            'i': int,
            'f': float,
            's': str,
            'dt': parse_iso8601,
            'n': lambda _: None,
        },
        more_element_types,
    ]
    for loader_map in loader_maps:
        loader = loader_map.get(packed_value[0])
        if loader is not None:
            return loader(packed_value[1])
    raise ValueError('cannot load %r' % packed_value[1])
