__all__ = [
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
        if self.timestamps[0] + self.period < self.clock():
            return True
        return False

    def count(self, raises=Disconnected):
        self.timestamps.append(self.clock())
        if self.connected:
            return True
        elif raises:
            raise raises
        else:
            return False


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
async def tcp_server(exit, create_server):
    """Wrap a TCP server in a process."""
    LOG.info('start server')
    server = await create_server()
    LOG.info('serving...')
    try:
        await exit
    finally:
        LOG.info('stop server')
        server.close()
        try:
            await server.wait_closed()
        except Exception:
            LOG.exception('err when closing server')


async def timer(timeout, *, raises=asyncio.TimeoutError, loop=None):
    """Wait until timeout.  If timeout is None or negative, wait forever."""
    if timeout is None or timeout < 0:
        await asyncio.Event(loop=loop).wait()  # Wait forever.
    else:
        await asyncio.sleep(timeout, loop=loop)
        if raises:
            raise raises
