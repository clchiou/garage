"""Common timer operations.

Examples:
>>> condition = threading.Condition()
>>> timers.make(timeout=10)
>>> with condition:
...     condition.wait(timer.get_timeout())
"""

__all__ = [
    'make',
]

import logging
import time

from g1.bases.assertions import ASSERT

LOG = logging.getLogger(__name__)


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
