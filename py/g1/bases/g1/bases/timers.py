"""Common timer operations.

Examples:
>>> condition = threading.Condition()
>>> timer = timers.make(timeout=10)
>>> with condition:
...     condition.wait(timer.get_timeout())
"""

__all__ = [
    'Stopwatch',
    'TimeUnits',
    'make',
    'timeout_to_key',
]

import enum
import time

from .assertions import ASSERT


class TimeUnits(enum.Enum):
    SECONDS = enum.auto()
    NANOSECONDS = enum.auto()


class Stopwatch:
    """Measure amounts of time.

    By default, it uses ``time.perf_counter_ns``, which should be good
    for measuring wall-clock time of a function call.  For other use
    cases, try ``time.monotonic_ns``, which should be good for measuring
    long time durations, or ``time.process_time_ns``, which should be
    good for measuring (system and user) CPU time of a function call.
    """

    def __init__(self, *, clock=time.perf_counter_ns):
        self._clock = clock
        self._duration = None
        self._start = None

    def start(self):
        ASSERT.none(self._start)
        self._duration = None
        self._start = self._clock()

    def stop(self):
        now = self._clock()
        ASSERT.not_none(self._start)
        self._duration = now - self._start
        self._start = None

    def get_duration(self, unit=TimeUnits.SECONDS):
        if self._start is not None:
            duration_ns = self._clock() - self._start
        else:
            duration_ns = ASSERT.not_none(self._duration)
        if unit is TimeUnits.SECONDS:
            return duration_ns / 1e9
        else:
            ASSERT.is_(unit, TimeUnits.NANOSECONDS)
            return duration_ns


def make(timeout):
    """Return a timer object instance."""
    if timeout is None:
        return BLOCKING_TIMER
    elif timeout <= 0:
        return EXPIRED_TIMER
    else:
        return Timer(timeout)


class Timer:

    def __init__(self, timeout):
        self._timeout = ASSERT.not_none(timeout)
        self._start = time.monotonic()
        self._end = self._start + self._timeout
        self._started = True

    def _now(self):
        return ASSERT.greater(time.monotonic(), self._start)

    def start(self):
        self._start = time.monotonic()
        self._end = self._start + self._timeout
        self._started = True

    def stop(self):
        """Stop the timer and reduce timeout accordingly."""
        self._timeout -= self._now() - self._start
        self._started = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()

    def is_expired(self):
        return self.get_timeout() <= 0

    def get_timeout(self):
        ASSERT.true(self._started)
        return self._end - self._now()


#
# The semantics of ``BlockingTimer`` and ``ExpiredTimer`` is subtly
# different from ``Timer``.  For now this difference is unimportant, but
# eventually we might need to address this difference.
#


class BlockingTimer:

    @staticmethod
    def start():
        pass

    @staticmethod
    def stop():
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    @staticmethod
    def is_expired():
        return False

    @staticmethod
    def get_timeout():
        return None


BLOCKING_TIMER = BlockingTimer()


class ExpiredTimer:

    @staticmethod
    def start():
        pass

    @staticmethod
    def stop():
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    @staticmethod
    def is_expired():
        return True

    @staticmethod
    def get_timeout():
        return 0


EXPIRED_TIMER = ExpiredTimer()

INFINITE = float('+inf')


def timeout_to_key(timeout):
    """Convert ``timeout`` to numeric value suitable for sorting."""
    if timeout is None:
        return INFINITE
    else:
        return timeout
