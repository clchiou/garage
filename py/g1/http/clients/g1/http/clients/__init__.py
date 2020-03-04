"""Asynchronous HTTP session backed by an executor.

This session class is a very leaky abstraction of ``requests.Session``,
but its interface is deliberately made different from ``requests`` for
the ease of programmatic use cases.
"""

__all__ = [
    'Request',
    'Session',
]

import logging

# Re-export these.
from .bases import Request
from .clients import Session

logging.getLogger(__name__).addHandler(logging.NullHandler())
