__all__ = [
    'Timeout',
    'call_with_kernel',
    'get_kernel',
    'run',
    'with_kernel',
]

import contextvars
import functools
import logging

from . import contexts
from . import kernels

# Re-export errors.
from .errors import Timeout

logging.getLogger(__name__).addHandler(logging.NullHandler())


def with_kernel(func):
    """Wrap ``func`` that it is called within a kernel context."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return call_with_kernel(func, *args, **kwargs)

    return wrapper


def call_with_kernel(func, *args, **kwargs):
    """Call ``func`` within a kernel context.

    The kernel object is closed on return.
    """

    def caller():
        kernel = kernels.Kernel()
        contexts.set_kernel(kernel)
        try:
            return func(*args, **kwargs)
        finally:
            kernel.close()

    return contextvars.copy_context().run(caller)


def run(awaitable=None, timeout=None):
    return contexts.get_kernel().run(awaitable, timeout)


def get_kernel():
    return contexts.get_kernel(None)
