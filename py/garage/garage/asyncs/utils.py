__all__ = [
    'IteratorAdapter',
    'CircuitBreaker',
    'synchronous',
    'tcp_server',
    'timer',
]

import asyncio
import collections
import logging
import time
from functools import wraps

from garage.asyncs.processes import process


LOG = logging.getLogger(__name__)


class IteratorAdapter:
    """Run a synchronous iterator in an executor."""

    def __init__(self, executor, iterator):
        self.executor = executor
        self.iterator = iterator

    async def __aiter__(self):
        return self

    async def __anext__(self):
        # next(iterator) raises StopIteration, which messes up async
        # event loop; so we have to detect it explicitly.
        value_future = self.executor.submit(next, self.iterator)
        await value_future  # This won't raise StopIteration.
        try:
            return value_future.result()
        except StopIteration:
            raise StopAsyncIteration from None


class CircuitBreaker:
    """Break (disconnect) when no less than `count` errors happened
       within last `period` seconds.
    """

    class Disconnected(Exception):
        pass

    def __init__(self, *, count, period, clock=None):
        self.timestamps = collections.deque(maxlen=count)
        self.period = period
        self.clock = clock or time.monotonic

    @property
    def connected(self):
        if len(self.timestamps) < self.timestamps.maxlen:
            return True
        if (self.period is not None and
                self.timestamps[0] + self.period < self.clock()):
            return True
        return False

    def ensure_connected(self, raises=Disconnected):
        if not self.connected:
            raise raises

    def trigger(self):
        self.timestamps.append(self.clock())


def synchronous(coro_func):
    """Transform the decorated coroutine function into a synchronous
       function.
    """
    @wraps(coro_func)
    def wrapper(*args, **kwargs):
        return asyncio.get_event_loop().run_until_complete(
            coro_func(*args, **kwargs))
    return wrapper


@process
async def tcp_server(exit, create_server, *, name=None):
    """Wrap a TCP server in a process."""
    name = name or 'tcp_server'
    LOG.info('%s: create server', name)
    server = await create_server()
    LOG.info('%s: start serving', name)
    try:
        await exit
    finally:
        LOG.info('%s: stop server', name)
        server.close()
        try:
            await server.wait_closed()
        except Exception:
            LOG.exception('%s: err when closing server', name)


async def timer(timeout, *, raises=asyncio.TimeoutError, loop=None):
    """Wait until timeout.  If timeout is None or negative, wait forever."""
    if timeout is None or timeout < 0:
        await asyncio.Event(loop=loop).wait()  # Wait forever.
    else:
        await asyncio.sleep(timeout, loop=loop)
    if raises:
        raise raises
