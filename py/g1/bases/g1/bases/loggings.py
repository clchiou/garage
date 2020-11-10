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

    def __call__(self, period, log, *args, **kwargs):
        location = get_location(2)
        with self._lock:
            num_calls = self._num_calls.setdefault(location, 0)
            self._num_calls[location] = num_calls + 1
            if num_calls % period != 0:
                return
        log(*args, **kwargs)


ONCE_PER = OncePer()
