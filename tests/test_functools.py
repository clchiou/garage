import unittest

from garage.functools import run_once
from garage.functools import is_ordered
from garage.functools import unique
from garage.functools import group
from garage.functools import with_defaults
from garage.functools import memorize
from garage.functools import nondata_property


class FunctoolsTest(unittest.TestCase):

    def test_run_once(self):
        logs = []
        def foo(i):
            logs.append(i)

        f = run_once(foo)
        for i in range(10):
            f(i)
        self.assertListEqual([0], logs)

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

    def test_unique(self):
        self.assertListEqual([], unique([]))
        self.assertListEqual([1], unique([1, 1, 1]))
        self.assertListEqual([1, 3, 2, 4], unique([1, 1, 3, 2, 3, 2, 4, 1]))

    def test_unique_by_key(self):
        self.assertListEqual([], unique([], key=lambda _: None))
        self.assertListEqual(
            ['a1', 'b2'],
            unique(['a1', 'b2', 'a2', 'b1'], key=lambda x: x[0]),
        )

    def test_group(self):
        self.assertListEqual([[3], [1], [2]], group([3, 1, 2]))
        self.assertListEqual(
            [[3, 3, 3], [1], [2, 2]], group([3, 1, 2, 3, 2, 3]))

    def test_with_defaults(self):

        def func(*args, **kwargs):
            return args, kwargs

        func2 = with_defaults(func, {'x': 1, 'y': 2})
        args, kwargs = func2('a', 'b', 'c', z=3)
        self.assertTupleEqual(('a', 'b', 'c'), args)
        self.assertDictEqual(dict(x=1, y=2, z=3), kwargs)


class Foo:

    def __init__(self, counter):
        self.counter = counter

    # Methods will be called only once.

    @memorize
    def prop(self):
        counter = self.counter
        self.counter -= 1
        return counter


class MemorizeTest(unittest.TestCase):

    def test_memorize(self):
        foo = Foo(100)
        self.assertIsNone(foo.__dict__.get('prop'))
        self.assertEqual(100, foo.prop)
        self.assertEqual(100, foo.prop)
        self.assertEqual(100, foo.__dict__['prop'])
        self.assertEqual(99, foo.counter)


class Bar:

    @nondata_property
    def prop1(self):
        """Doc string."""
        return 'prop1-value'

    prop2 = nondata_property()


class NondataPropertyTest(unittest.TestCase):

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

    def test_nondata_property_override(self):
        class Base:
            @nondata_property
            def prop(self):
                raise AssertionError

        class Ext1(Base):
            prop = 1

        class Ext2(Base):
            def __init__(self):
                self.prop = 1

        class Ext3(Base):
            @nondata_property
            def prop(self):
                return 1

        class Ext4(Base):
            @property
            def prop(self):
                return 1

        for cls in (Ext1, Ext2, Ext3, Ext4):
            self.assertEqual(1, cls().prop)

        with self.assertRaises(AssertionError):
            Base().prop


if __name__ == '__main__':
    unittest.main()
