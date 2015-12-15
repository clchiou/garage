"""Python extension for V8 JavaScript engine."""

import logging

from .v8 import V8

logging.getLogger(__name__).addHandler(logging.NullHandler())
