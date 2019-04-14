__all__ = [
    'VOID',
    'VoidType',
]

import logging

# Re-export these.
from ._capnp import (  # pylint: disable=no-name-in-module
    VOID, VoidType,
)

logging.getLogger(__name__).addHandler(logging.NullHandler())
