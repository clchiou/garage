import unittest

from garage import classes
from garage import functools


class ClassesTest(unittest.TestCase):

    def test_lazy_attrs(self):

        names = []
        def compute_attrs(name, attrs):
            names.append(name)
            attrs[name] = name

        class Foo(classes.LazyAttrs):

            def __init__(self):
                super().__init__(compute_attrs)

            @property
            def x(self):
                return 1

            @functools.memorize
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


if __name__ == '__main__':
    unittest.main()
