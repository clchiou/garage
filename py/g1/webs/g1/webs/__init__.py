"""A simple/naive web application server.

This is designed based on our experience and use cases, and thus is not
a generic or powerful application server.
"""

__all__ = [
    'Application',
    'HttpError',
    'Request',
    'Response',
]

import logging

from . import consts
from . import wsgi_apps

# Re-export these.
from .consts import *
from .wsgi_apps import *

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = consts.__all__ + wsgi_apps.__all__
