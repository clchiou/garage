import unittest

from g1.bases import classes


class SingletonMetaTest(unittest.TestCase):

    def test_singleton(self):

        self.assertIsInstance(classes.SingletonMeta, type)

        xs = []

        class Foo(metaclass=classes.SingletonMeta):

            def __init__(self, x):
                xs.append(x)

        f1 = Foo(1)
        f2 = Foo(2)
        self.assertIs(f1, f2)
        self.assertEqual(xs, [1])


class NondataPropertyTest(unittest.TestCase):

    def test_nondata_property(self):

        class Test:

            @classes.nondata_property
            def nondata(self):  # pylint: disable=no-self-use
                """Doc string."""
                return 1

            @property
            def data(self):
                return 2

        self.assertEqual(Test.nondata.__doc__, 'Doc string.')

        t0 = Test()
        self.assertEqual(t0.nondata, 1)
        self.assertEqual(t0.data, 2)

        t0.nondata = 3
        with self.assertRaises(AttributeError):
            t0.data = 4
        self.assertEqual(t0.nondata, 3)
        self.assertEqual(t0.data, 2)

        # Not affected by t0.
        t1 = Test()
        self.assertEqual(t1.nondata, 1)
        self.assertEqual(t1.data, 2)

    def test_memorizing_property(self):

        called = []

        class Test:

            def __init__(self, x):
                self.x = x

            @classes.memorizing_property
            def p0(self):
                """Doc string."""
                called.append(('p0', self.x))
                return self.x + 1

            @classes.memorizing_property
            def p1(self):
                called.append(('p1', self.x))
                return self.x + 2

        self.assertEqual(Test.p0.__doc__, 'Doc string.')

        t0 = Test(0)
        t1 = Test(1)
        self.assertEqual(called, [])

        for _ in range(10):
            self.assertEqual(t0.p0, 1)
            self.assertEqual(called, [('p0', 0)])
        self.assertIn('p0', t0.__dict__)
        self.assertNotIn('p1', t0.__dict__)
        self.assertNotIn('p0', t1.__dict__)
        self.assertNotIn('p1', t1.__dict__)

        for _ in range(10):
            self.assertEqual(t0.p1, 2)
            self.assertEqual(called, [('p0', 0), ('p1', 0)])
        self.assertIn('p0', t0.__dict__)
        self.assertIn('p1', t0.__dict__)
        self.assertNotIn('p0', t1.__dict__)
        self.assertNotIn('p1', t1.__dict__)

        self.assertEqual(t0.p0, 1)
        self.assertEqual(t0.p1, 2)
        self.assertEqual(called, [('p0', 0), ('p1', 0)])

        self.assertEqual(called, [('p0', 0), ('p1', 0)])
        for _ in range(10):
            self.assertEqual(t1.p0, 2)
            self.assertEqual(called, [('p0', 0), ('p1', 0), ('p0', 1)])
        for _ in range(10):
            self.assertEqual(t1.p1, 3)
            self.assertEqual(
                called, [('p0', 0), ('p1', 0), ('p0', 1), ('p1', 1)]
            )
        self.assertIn('p0', t0.__dict__)
        self.assertIn('p1', t0.__dict__)
        self.assertIn('p0', t1.__dict__)
        self.assertIn('p1', t1.__dict__)


class MakeReprTest(unittest.TestCase):

    def test_make_repr(self):

        class Foo:

            class Bar:
                x = 1
                y = 2

        obj = Foo.Bar()
        prefix = '%s.%s %#x' % (
            Foo.Bar.__module__, Foo.Bar.__qualname__, id(obj)
        )

        r = classes.make_repr()
        self.assertEqual(r(obj), f'<{prefix}>')

        r = classes.make_repr('x={self.x} y={self.y}')
        self.assertEqual(r(obj), f'<{prefix} x=1 y=2>')

        r = classes.make_repr('sum={sum}', sum=lambda self: self.x + self.y)
        self.assertEqual(r(obj), f'<{prefix} sum=3>')

        with self.assertRaises(AssertionError):
            classes.make_repr('{}', self=None)
        with self.assertRaises(AssertionError):
            classes.make_repr('{}', __self_id=None)
        with self.assertRaises(AssertionError):
            classes.make_repr(x=lambda self: self.x)


if __name__ == '__main__':
    unittest.main()
