__all__ = [
    'synchronous',
    'timeout_after',
]

from functools import wraps

import curio


def synchronous(coro_func):
    """Transform the decorated coroutine function into a synchronous
       function.
    """
    @wraps(coro_func)
    def wrapper(*args, **kwargs):
        return curio.run(coro_func(*args, **kwargs))
    return wrapper


def timeout_after(seconds, coro=None):
    """Wrap curio.timeout_after for non-positive seconds argument."""
    if seconds is None or seconds <= 0:
        if coro is None:
            return _TimeoutNever()
        else:
            return coro
    else:
        return curio.timeout_after(seconds, coro=coro)


class _TimeoutNever:

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass
