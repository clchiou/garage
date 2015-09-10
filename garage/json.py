"""Helpers for standard library's json package."""

__all__ = [
    'encode_mapping',
]

from collections import Mapping
from collections import OrderedDict


def encode_mapping(obj):
    if isinstance(obj, Mapping):
        # Preserve ordering in the Mapping object.
        return OrderedDict(obj.items())
    raise TypeError(repr(obj) + ' is not JSON serializable')
