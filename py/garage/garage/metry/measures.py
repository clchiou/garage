__all__ = [
    'Measurement',
    'make_counter',
    'make_rater',
    'make_timer',
]

import collections
import functools
import time


Measurement = collections.namedtuple('Measurement', 'when value duration')


def make_counter(metry, name):
    return functools.partial(count, metry.measure, name)


def make_rater(metry, name):
    return functools.partial(rate, metry.measure, name)


def make_timer(metry, name):
    return Timer(metry.measure, name)


def count(measure, name, value=1):
    measure(name, Measurement(time.time(), value, None))


def rate(measure, name, value):
    return MeasureContext(measure, name, value)


class Timer:

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
        return MeasureContext(self.measure, self.name, None)


class MeasureContext:

    def __init__(self, measure, measure_name, value):
        self.measure = measure
        self.measure_name = measure_name
        self.value = value
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
        measurement = Measurement(self._time, self.value, elapsed)
        self.measure(self.measure_name, measurement)
        self._start = None  # Disable context.
