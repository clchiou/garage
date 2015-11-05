import unittest

from garage.classes import *


class ClassesTest(unittest.TestCase):

    def test_lazy_attrs(self):

        names = []
        def compute_attrs(name, attrs):
            names.append(name)
            attrs[name] = name

        class Foo(LazyAttrs):

            def __init__(self):
                super().__init__(compute_attrs)

            @property
            def x(self):
                return 1

            @memorize
            def y(self):
                return 2

        foo = Foo()
        foo.z = 3
        for _ in range(3):  # Call them repeatedly.
            self.assertEqual('name', foo.name)
            self.assertEqual('foo', foo.foo)
            self.assertEqual('bar', foo.bar)
            self.assertEqual(1, foo.x)
            self.assertEqual(2, foo.y)
            self.assertEqual(3, foo.z)
        self.assertListEqual(['name', 'foo', 'bar'], names)


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
