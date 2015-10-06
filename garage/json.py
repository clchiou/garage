"""Helpers for standard library's json package."""

__all__ = [
    'encode_datetime',
    'encode_mapping',
    'join_encoders',
]

import datetime
from collections import Mapping
from collections import OrderedDict


def _type_error(obj):
    return TypeError(repr(obj) + ' is not JSON serializable')


def encode_datetime(obj, datetime_format=None):
    if not isinstance(obj, datetime.datetime):
        raise _type_error(obj)
    if datetime_format is None:
        return obj.isoformat()
    else:
        return obj.strftime(datetime_format)


def encode_mapping(obj):
    if not isinstance(obj, Mapping):
        raise _type_error(obj)
    if isinstance(obj, OrderedDict):
        return obj
    else:
        # Preserve ordering in the Mapping object.
        return OrderedDict(obj.items())


def join_encoders(*encoders):
    def encoder(obj):
        for enc in encoders:
            try:
                return enc(obj)
            except TypeError:
                pass
        raise _type_error(obj)
    return encoder
