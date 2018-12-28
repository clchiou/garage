"""Manage global kernel instance with ``contextvars``."""

__all__ = [
    # Kernel.
    'get_kernel',
    'set_kernel',
    # Current task.
    'get_current_task',
    'setting_current_task',
]

import contextlib
import contextvars

KERNEL = contextvars.ContextVar('kernel')

get_kernel = KERNEL.get

set_kernel = KERNEL.set

CURRENT_TASK = contextvars.ContextVar('current_task')

get_current_task = CURRENT_TASK.get


@contextlib.contextmanager
def setting_current_task(current_task):
    token = CURRENT_TASK.set(current_task)
    try:
        yield
    finally:
        CURRENT_TASK.reset(token)
