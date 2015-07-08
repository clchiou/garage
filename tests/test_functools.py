import unittest

from garage.functools import memorize


class Foo:

    def __init__(self):
        self.counter1 = 1
        self.counter2 = 2

    # 1. Decoration order is irrelevant.
    # 2. Only called once.

    @memorize
    @property
    def prop1(self):
        counter = self.counter1
        self.counter1 -= 1
        return counter

    @property
    @memorize
    def prop2(self):
        counter = self.counter2
        self.counter2 -= 1
        return counter


class TestMemorize(unittest.TestCase):

    def test_memorize(self):
        foo = Foo()
        self.assertEqual(1, foo.prop1)
        self.assertEqual(1, foo.prop1)
        self.assertEqual(2, foo.prop2)
        self.assertEqual(2, foo.prop2)


if __name__ == '__main__':
    unittest.main()
