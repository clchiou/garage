import unittest

from garage.intervals import POS_INF
from garage.intervals import NEG_INF
from garage.intervals import BoundType
from garage.intervals import IntegerInterval
from garage.intervals import parse


class ExtremeValueTest(unittest.TestCase):

    def test_extreme_value(self):
        self.assertLess(NEG_INF, POS_INF)
        self.assertLess(NEG_INF, -1)
        self.assertLess(NEG_INF, 0)
        self.assertLess(NEG_INF, +1)
        self.assertLess(-1, POS_INF)
        self.assertLess(0, POS_INF)
        self.assertLess(+1, POS_INF)


class BoundTypeTest(unittest.TestCase):

    def test_bound_type(self):
        self.assertIs(BoundType.OPEN, ~BoundType.CLOSED)
        self.assertIs(BoundType.CLOSED, ~BoundType.OPEN)


class IntervalTest(unittest.TestCase):

    def test_empty_interval(self):
        for interval in (
                IntegerInterval(0, BoundType.CLOSED, 0, BoundType.OPEN),
                IntegerInterval(0, BoundType.OPEN, 0, BoundType.CLOSED),
                IntegerInterval(0, BoundType.OPEN, 0, BoundType.OPEN)):
            self.assertFalse(interval)
            for i in range(-3, 4):
                self.assertNotIn(i, interval)

    def test_unit_interval(self):
        interval = IntegerInterval(0, BoundType.CLOSED, 0, BoundType.CLOSED)
        self.assertTrue(interval)
        self.assertIn(0, interval)
        for i in range(1, 4):
            self.assertNotIn(+i, interval)
            self.assertNotIn(-i, interval)

    def test_integer_interval(self):
        interval = IntegerInterval(0, BoundType.CLOSED, 2, BoundType.OPEN)
        self.assertNotIn(NEG_INF, interval)
        self.assertNotIn(-1, interval)
        self.assertIn(0, interval)
        self.assertIn(1, interval)
        self.assertNotIn(2, interval)
        self.assertNotIn(POS_INF, interval)

        interval = ~interval
        self.assertIn(NEG_INF, interval)
        self.assertIn(-1, interval)
        self.assertNotIn(0, interval)
        self.assertNotIn(1, interval)
        self.assertIn(2, interval)
        self.assertIn(POS_INF, interval)

    def test_and(self):
        p = IntegerInterval(0, BoundType.CLOSED, 4, BoundType.CLOSED)
        q = IntegerInterval(2, BoundType.CLOSED, 6, BoundType.CLOSED)
        interval = p & q
        self.assertNotIn(1, interval)
        self.assertIn(2, interval)
        self.assertIn(3, interval)
        self.assertIn(4, interval)
        self.assertNotIn(5, interval)

    def test_or(self):
        p = IntegerInterval(0, BoundType.CLOSED, 4, BoundType.CLOSED)
        q = IntegerInterval(2, BoundType.CLOSED, 6, BoundType.CLOSED)
        interval = p | q
        self.assertNotIn(-1, interval)
        for i in range(0, 7):
            self.assertIn(i, interval)
        self.assertNotIn(7, interval)

    def test_xor(self):
        p = IntegerInterval(0, BoundType.CLOSED, 4, BoundType.CLOSED)
        q = IntegerInterval(2, BoundType.CLOSED, 6, BoundType.CLOSED)
        interval = p ^ q
        self.assertNotIn(-1, interval)
        self.assertIn(0, interval)
        self.assertIn(1, interval)
        self.assertNotIn(2, interval)
        self.assertNotIn(3, interval)
        self.assertNotIn(4, interval)
        self.assertIn(5, interval)
        self.assertIn(6, interval)
        self.assertNotIn(7, interval)

    def test_filter(self):
        interval = parse('3-5')
        self.assertListEqual([3, 4, 5], list(interval.filter(range(10))))
        interval = parse('3-5,8-')
        self.assertListEqual([3, 4, 5, 8, 9], list(interval.filter(range(10))))
        interval = parse('-2')
        self.assertListEqual(
            ['a', 'ab'],
            list(interval.filter(['a', 'ab', 'abc', 'abcd'], key=len)),
        )


class ParseTest(unittest.TestCase):

    def test_unit_interval(self):
        interval = parse('3')
        self.assertNotIn(NEG_INF, interval)
        self.assertNotIn(2, interval)
        self.assertIn(3, interval)
        self.assertNotIn(4, interval)
        self.assertNotIn(POS_INF, interval)

        interval = ~interval
        self.assertIn(NEG_INF, interval)
        self.assertIn(2, interval)
        self.assertNotIn(3, interval)
        self.assertIn(4, interval)
        self.assertIn(POS_INF, interval)

    def test_points(self):
        interval = parse('1,3,5,7,9')
        self.assertNotIn(0, interval)
        self.assertNotIn(2, interval)
        self.assertNotIn(4, interval)
        self.assertNotIn(6, interval)
        self.assertNotIn(8, interval)
        self.assertNotIn(10, interval)
        self.assertIn(1, interval)
        self.assertIn(3, interval)
        self.assertIn(5, interval)
        self.assertIn(7, interval)
        self.assertIn(9, interval)

    def test_interval(self):
        interval = parse('1-4')
        self.assertNotIn(0, interval)
        self.assertNotIn(5, interval)
        for i in range(1, 5):
            self.assertIn(i, interval)

        interval = parse('-0')
        self.assertIn(NEG_INF, interval)
        self.assertIn(0, interval)
        self.assertNotIn(1, interval)

        interval = parse('0-')
        self.assertIn(POS_INF, interval)
        self.assertIn(0, interval)
        self.assertNotIn(-1, interval)

        interval = parse('-')
        self.assertIn(POS_INF, interval)
        self.assertIn(NEG_INF, interval)
        self.assertIn(1, interval)
        self.assertIn(0, interval)
        self.assertIn(-1, interval)


if __name__ == '__main__':
    unittest.main()
