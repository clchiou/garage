import unittest

from garage.functools import is_ordered
from garage.functools import memorize
from garage.functools import nondata_property


class TestIsOrdered(unittest.TestCase):

    def test_is_ordered(self):
        self.assertTrue(is_ordered([]))
        self.assertTrue(is_ordered([1]))
        self.assertTrue(is_ordered([1, 1]))
        self.assertTrue(is_ordered([1, 1, 1]))
        self.assertTrue(is_ordered([1, 2]))
        self.assertTrue(is_ordered([1, 2, 3]))

        self.assertFalse(is_ordered([2, 1]))
        self.assertFalse(is_ordered([1, 3, 2]))

        self.assertTrue(is_ordered([], strict=True))
        self.assertTrue(is_ordered([1], strict=True))
        self.assertTrue(is_ordered([1, 2], strict=True))
        self.assertTrue(is_ordered([1, 2, 3], strict=True))

        self.assertFalse(is_ordered([1, 1], strict=True))
        self.assertFalse(is_ordered([1, 1, 1], strict=True))
        self.assertFalse(is_ordered([2, 1], strict=True))
        self.assertFalse(is_ordered([1, 3, 2], strict=True))


class Foo:

    def __init__(self, counter1, counter2):
        self.counter1 = counter1
        self.counter2 = counter2

    # Methods will be called only once.

    @memorize
    def prop1(self):
        counter = self.counter1
        self.counter1 -= 1
        return counter

    @memorize
    def prop2(self):
        counter = self.counter2
        self.counter2 -= 1
        return counter


class TestMemorize(unittest.TestCase):

    def test_memorize(self):
        foo = Foo(1, 2)
        self.assertEqual(1, foo.prop1)
        self.assertEqual(1, foo.prop1)
        self.assertEqual(2, foo.prop2)
        self.assertEqual(2, foo.prop2)
        foo2 = Foo(100, 200)
        self.assertEqual(100, foo2.prop1)
        self.assertEqual(100, foo2.prop1)
        self.assertEqual(200, foo2.prop2)
        self.assertEqual(200, foo2.prop2)


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
