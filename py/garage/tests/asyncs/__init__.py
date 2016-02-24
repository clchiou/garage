import asyncio
from functools import wraps


def synchronous(coro_method):
    @wraps(coro_method)
    def decorated(self):
        asyncio.get_event_loop().run_until_complete(coro_method(self))
    return decorated
