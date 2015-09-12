"""Helpers for standard library's json package."""

__all__ = [
    'encode_datetime',
    'encode_mapping',
    'join_encoders',
]

import datetime
from collections import Mapping
from collections import OrderedDict


# ISO 8601 date and time format with time zone designator.
DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%f%z'


def _type_error(obj):
    return TypeError(repr(obj) + ' is not JSON serializable')


def encode_datetime(obj, datetime_format=DATETIME_FORMAT):
    if not isinstance(obj, datetime.datetime):
        raise _type_error(obj)
    return obj.strftime(datetime_format)


def encode_mapping(obj):
    if not isinstance(obj, Mapping):
        raise _type_error(obj)
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
