__all__ = [
    'ONCE_PER',
]

import sys
import threading
import time

from . import times
from .assertions import ASSERT

ASSERT(hasattr(sys, '_getframe'), 'expect sys._getframe')


def get_location(depth):
    frame = sys._getframe(depth)
    return frame.f_code.co_filename, frame.f_lineno


class OncePer:

    def __init__(self):
        self._lock = threading.Lock()
        self._records = {}

    # NOTE: You must call __check at the same depth of call stack so
    # that get_location returns your caller correctly.
    def __check(self, interval, unit):
        location = get_location(3)
        with self._lock:
            if unit is None:
                num_calls = self._records.setdefault(location, 0)
                self._records[location] = num_calls + 1
                if num_calls % interval != 0:
                    return False
            else:
                now = time.monotonic_ns()
                last = self._records.get(location)
                if (\
                    last is not None and
                    last +
                    times.convert(unit, times.Units.NANOSECONDS, interval)
                    > now
                ):
                    return False
                self._records[location] = now
        return True

    def check(self, interval, unit=None):
        return self.__check(interval, unit)

    def __call__(self, interval, log, *args, **kwargs):
        if self.__check(interval, None):
            log(*args, **kwargs)


ONCE_PER = OncePer()
