__all__ = [
    'call_with_kernel',
    'run',
    'with_kernel',
    # Contexts.
    'get_all_tasks',
    'get_current_task',
    'get_kernel',
    # Errors.
    'Cancelled',
    'Timeout',
    # Traps.
    'sleep',
    'spawn',
    'timeout_after',
]

import contextvars
import functools
import logging

from . import contexts
from . import kernels
# Re-export these symbols.
from .errors import Cancelled
from .errors import Timeout
from .traps import sleep

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


def _get_or_create_kernel():
    try:
        return contexts.get_kernel()
    except LookupError:
        pass
    # Implicitly create a global kernel instance.
    contexts.set_kernel(kernels.Kernel())
    return contexts.get_kernel()


def run(awaitable=None, timeout=None):
    return _get_or_create_kernel().run(awaitable, timeout)


def spawn(awaitable):
    # Use ``_get_or_create_kernel`` to allow users to call ``spawn``
    # without first initializing a kernel context.
    return _get_or_create_kernel().spawn(awaitable)


def timeout_after(duration):
    kernel = contexts.get_kernel()
    task = kernel.get_current_task()
    if not task:
        raise LookupError('no current task: %r' % kernel)
    return kernel.timeout_after(task, duration)


#
# Contexts.
#
# Don't (implicitly) create kernel for these functions.
#


def get_kernel():
    return contexts.get_kernel(None)


def get_all_tasks():
    kernel = get_kernel()
    return kernel.get_all_tasks() if kernel else []


def get_current_task():
    kernel = get_kernel()
    return kernel.get_current_task() if kernel else None
