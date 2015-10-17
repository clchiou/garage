__all__ = [
    'make_counter',
    'make_timer',
]

import collections
import functools
import time


def make_counter(metry, name):
    return functools.partial(count, metry.measure, name)


Count = collections.namedtuple('Count', 'time value')


def count(measure, name, value=1):
    measure(name, Count(time.time(), value))


def make_timer(metry, name):
    return Timer(metry.measure, name)


Time = collections.namedtuple('Time', 'start elapsed')


class Timer:

    class Context:

        def __init__(self, timer):
            self.timer = timer
            self._time = None
            self._start = None

        def __enter__(self):
            self.start()
            return self

        def __exit__(self, *_):
            self.stop()

        def start(self):
            self._time = time.time()
            self._start = time.perf_counter()

        def stop(self):
            if self._start is None:
                return
            elapsed = time.perf_counter() - self._start
            self.timer.measure(self.timer.name, Time(self._time, elapsed))
            self._time = None
            self._start = None

    def __init__(self, measure, name):
        self.measure = measure
        self.name = name

    def __call__(self, func):
        @functools.wraps(func)
        def timed_func(*args, **kwargs):
            with self.time():
                return func(*args, **kwargs)
        return timed_func

    def time(self):
        return Timer.Context(self)
