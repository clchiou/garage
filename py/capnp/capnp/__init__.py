"""Provide a Pythonic API layer on top of the native extension.

If you don't like this API layer, you may use the capnp.native module
directly, which offers a 1:1 mapping to Cap'n Proto C++ API.

This module provides three groups of functionalities:
* Load and traverse schema objects.
* Access Cap'n Proto data dynamically with reflection.
"""

__all__ = [
    'AnnotationDef',
    'Schema',
    'SchemaLoader',
    'Type',

    'MessageBuilder',
    'MessageReader',

    'DynamicObject',
    'register_converter',
    'register_serializer',
]

import logging

from .dynamics import MessageBuilder
from .dynamics import MessageReader

from .objects import DynamicObject
from .objects import register_converter
from .objects import register_serializer

from .schemas import AnnotationDef
from .schemas import Schema
from .schemas import SchemaLoader
from .schemas import Type


logging.getLogger(__name__).addHandler(logging.NullHandler())
