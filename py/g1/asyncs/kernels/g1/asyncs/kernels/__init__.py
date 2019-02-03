__all__ = [
    'call_with_kernel',
    'run',
    'with_kernel',
    # Errors.
    'Cancelled',
    'Timeout',
    # Traps.
    'get_all_tasks',
    'sleep',
    'spawn',
    'timeout_after',
    # Adapters.
    'CompletionQueueAdapter',
    'FileAdapter',
    'FutureAdapter',
    'SocketAdapter',
    # Locks.
    'Condition',
    'Event',
    'Lock',
    # Signals.
    'SignalQueue',
    # Utilities.
    'BytesStream',
    'StringStream',
    'TaskCompletionQueue',
]

import contextvars
import functools
import logging

from . import contexts
from . import kernels
# Re-export these symbols.
from .adapters import CompletionQueueAdapter
from .adapters import FileAdapter
from .adapters import FutureAdapter
from .adapters import SocketAdapter
from .errors import Cancelled
from .errors import Timeout
from .locks import Condition
from .locks import Event
from .locks import Lock
from .signals import SignalQueue
from .traps import sleep
from .utils import BytesStream
from .utils import StringStream
from .utils import TaskCompletionQueue

logging.getLogger(__name__).addHandler(logging.NullHandler())


def with_kernel(func):
    """Wrap ``func`` that it is called inside a kernel context."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return call_with_kernel(func, *args, **kwargs)

    return wrapper


def call_with_kernel(func, *args, **kwargs):
    """Call ``func`` within a context in which a kernel is created.

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


def get_all_tasks():
    return _get_or_create_kernel().get_all_tasks()


def spawn(awaitable):
    # Use ``_get_or_create_kernel`` so that users may call ``spawn`` out
    # of the event loop.
    return _get_or_create_kernel().spawn(awaitable)


def timeout_after(duration):
    return contexts.get_kernel().timeout_after(
        contexts.get_current_task(), duration
    )
