"""Manage global kernel instance with ``contextvars``."""

__all__ = [
    # Kernel.
    'get_kernel',
    'set_kernel',
]

import contextvars

KERNEL = contextvars.ContextVar('kernel')

get_kernel = KERNEL.get

set_kernel = KERNEL.set
