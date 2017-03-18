__all__ = [
    'synchronous',
]

from functools import wraps

try:
    import curio
except ImportError:
    curio = None


def synchronous(coro_func):
    """Transform the decorated coroutine function into a synchronous
       function.
    """
    @wraps(coro_func)
    def wrapper(*args, **kwargs):
        return curio.run(coro_func(*args, **kwargs))
    return wrapper
