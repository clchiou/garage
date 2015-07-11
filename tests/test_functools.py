import unittest

from garage.functools import memorize
from garage.functools import nondata_property


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


class Bar:

    @nondata_property
    def prop1(self):
        """Doc string."""
        return 'prop1-value'

    prop2 = nondata_property()


class TestNondataProperty(unittest.TestCase):

    def test_nondata_property(self):
        # This should not raise.
        self.assertTrue(Bar.prop1)
        self.assertEqual('Doc string.', Bar.prop1.__doc__)
        self.assertTrue(Bar.prop2)
        self.assertIsNone(Bar.prop2.__doc__)

        bar = Bar()
        self.assertEqual('prop1-value', bar.prop1)
        with self.assertRaises(AttributeError):
            bar.prop2
        # Override non-data descriptor.
        bar.prop2 = 'hello'
        self.assertEqual('hello', bar.prop2)


if __name__ == '__main__':
    unittest.main()
