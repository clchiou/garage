__all__ = [
    'ONCE_PER',
]

import sys
import threading

from .assertions import ASSERT

ASSERT(hasattr(sys, '_getframe'), 'expect sys._getframe')


def get_location(depth):
    frame = sys._getframe(depth)
    return frame.f_code.co_filename, frame.f_lineno


class OncePer:

    def __init__(self):
        self._lock = threading.Lock()
        self._num_calls = {}

    # NOTE: You must call __check at the same depth of call stack so
    # that get_location returns your caller correctly.
    def __check(self, period):
        location = get_location(3)
        with self._lock:
            num_calls = self._num_calls.setdefault(location, 0)
            self._num_calls[location] = num_calls + 1
            if num_calls % period != 0:
                return False
        return True

    def check(self, period):
        return self.__check(period)

    def __call__(self, period, log, *args, **kwargs):
        if self.__check(period):
            log(*args, **kwargs)


ONCE_PER = OncePer()
