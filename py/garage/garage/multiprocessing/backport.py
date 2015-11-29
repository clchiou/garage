__all__ = [
    'BoundedSemaphore',
    'UnlimitedSemaphore',
    'Timeout',
]

import threading
import time


# NOTE: This module is Python 2 compatible.


class Timeout(Exception):
    pass


# Because Python 2 semaphore does not support timeout...
class BoundedSemaphore(object):

    def __init__(self, value):
        if value < 0:
            raise ValueError('semaphore initial value must be >= 0')
        self._cond = threading.Condition(threading.Lock())
        self._initial_value = value
        self._value = value

    def acquire(self, timeout):
        with self._cond:
            endtime = time.time() + timeout
            while self._value == 0:
                timeout = endtime - time.time()
                if timeout <= 0:
                    raise Timeout
                self._cond.wait(timeout)
            self._value -= 1

    def release(self):
        with self._cond:
            if self._value >= self._initial_value:
                raise ValueError('semaphore is released too many times')
            self._value += 1
            self._cond.notify()


class UnlimitedSemaphore(object):

    def acquire(self, timeout):
        pass

    def release(self):
        pass
