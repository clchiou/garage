__all__ = [
    'make_counter',
]

import collections
import functools
import time


def make_counter(metry, name):
    return functools.partial(count, metry.measure, name)


Count = collections.namedtuple('Count', 'time value')


def count(measure, name, value=1):
    measure(name, Count(time.time(), value))
