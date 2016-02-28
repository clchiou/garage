__all__ = [
    'CircuitBreaker',
]

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

    def err(self, raises=Disconnected):
        self.timestamps.append(self.clock())
        if raises and not self.connected:
            raise raises
