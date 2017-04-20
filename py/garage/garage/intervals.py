__all__ = [
    'POS_INF',
    'NEG_INF',
    'BoundType',
    'IntegerInterval',
    'parse',
]

import re
from enum import Enum

from garage import asserts


POS_INF = float('+inf')
NEG_INF = float('-inf')


class BoundType(Enum):
    OPEN = 'OPEN'
    CLOSED = 'CLOSED'

    def __invert__(self):
        if self is BoundType.OPEN:
            return BoundType.CLOSED
        else:
            return BoundType.OPEN


class IntervalMixin:

    def __repr__(self):
        return 'Interval<%s>' % str(self)

    def __and__(self, other):
        return JointInterval(all, [self, other])

    def __or__(self, other):
        return JointInterval(any, [self, other])

    def __xor__(self, other):
        return (self & ~other) | (~self & other)

    def filter(self, iterable, key=None):
        if key is None:
            key = lambda item: item
        return filter(lambda item: key(item) in self, iterable)


class IntegerInterval(IntervalMixin):

    def __init__(self, left, left_type, right, right_type):
        asserts.precond(left <= right)
        asserts.type_of(left_type, BoundType)
        asserts.type_of(right_type, BoundType)
        self.left = left
        self.left_type = left_type
        self.right = right
        self.right_type = right_type

    def __str__(self):
        return ('%s%s, %s%s' % (
            '(' if self.left_type is BoundType.OPEN else '[',
            self.left,
            self.right,
            ')' if self.right_type is BoundType.OPEN else ']',
        ))

    def __bool__(self):
        if self.left == self.right:
            return (self.left_type is BoundType.CLOSED and
                    self.right_type is BoundType.CLOSED)
        elif self.left + 1 == self.right:
            return (self.left_type is BoundType.CLOSED or
                    self.right_type is BoundType.CLOSED)
        else:
            return True

    def __contains__(self, item):
        if not self:
            return False
        elif self.left < item < self.right:
            return True
        elif item == self.left:
            return self.left_type is BoundType.CLOSED
        elif item == self.right:
            return self.right_type is BoundType.CLOSED
        else:
            return False

    def __invert__(self):
        return (
            IntegerInterval(
                NEG_INF, BoundType.CLOSED, self.left, ~self.left_type) |
            IntegerInterval(
                self.right, ~self.right_type, POS_INF, BoundType.CLOSED))


class JointInterval(IntervalMixin):

    def __init__(self, join, intervals):
        asserts.precond(join in (all, any))
        self.join = join
        self.intervals = intervals

    def __str__(self):
        join_str = ' | ' if self.join is any else ' & '
        return join_str.join(map(str, self.intervals))

    def __bool__(self):
        return self.join(bool(interval) for interval in self.intervals)

    def __contains__(self, item):
        return self.join(item in interval for interval in self.intervals)

    def __invert__(self):
        join = all if self.join is any else any
        return JointInterval(join, [~interval for interval in self.intervals])


PATTERN_INTERVAL = re.compile(r'(\d*)-(\d*)')
PATTERN_NUMBER = re.compile(r'\d+')


def parse(interval_specs):
    return JointInterval(any, list(map(_parse, interval_specs.split(','))))


def _parse(interval_spec):
    match = PATTERN_INTERVAL.fullmatch(interval_spec)
    if match:
        if match.group(1):
            left = int(match.group(1))
        else:
            left = NEG_INF
        if match.group(2):
            right = int(match.group(2))
        else:
            right = POS_INF
        return IntegerInterval(left, BoundType.CLOSED, right, BoundType.CLOSED)

    match = PATTERN_NUMBER.fullmatch(interval_spec)
    if match:
        point = int(interval_spec)
        return IntegerInterval(
            point, BoundType.CLOSED, point, BoundType.CLOSED)

    raise SyntaxError('Cannot parse %r' % interval_spec)
