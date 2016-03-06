__all__ = [
    'CircuitBreaker',
    'timer',
]

import asyncio
import collections
import time


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


async def timer(timeout, *, raises=asyncio.TimeoutError, loop=None):
    """Wait until timeout.  If timeout is None or negative, wait forever."""
    if timeout is None or timeout < 0:
        await asyncio.Event(loop=loop).wait()  # Wait forever.
    else:
        await asyncio.sleep(timeout, loop=loop)
        if raises:
            raise raises
