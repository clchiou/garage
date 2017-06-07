"""Provide a Pythonic API layer on top of the native extension.

If you don't like this API layer, you may use the capnp.native module
directly, which offers a 1:1 mapping to Cap'n Proto C++ API.

This module provides three groups of functionalities:
* Load and traverse schema objects.
* Access Cap'n Proto data dynamically with reflection.
* Generate Python class from schema.
"""

__all__ = [
    'Schema',
    'SchemaLoader',

    'MessageBuilder',
    'MessageReader',

    'DynamicEnum',
    'DynamicList',
    'DynamicStruct',
]

import logging

from .dynamics import MessageBuilder
from .dynamics import MessageReader

from .dynamics import DynamicEnum
from .dynamics import DynamicList
from .dynamics import DynamicStruct

from .schemas import Schema
from .schemas import SchemaLoader


logging.getLogger(__name__).addHandler(logging.NullHandler())
