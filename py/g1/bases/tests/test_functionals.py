import unittest

from functools import partial

from g1.bases import functionals


class FunctionalsTest(unittest.TestCase):

    def test_identity(self):
        sentinel = object()
        self.assertIs(functionals.identity(sentinel), sentinel)

    def test_compose(self):

        sentinel = object()
        self.assertIs(functionals.compose()(sentinel), sentinel)

        inc = lambda i: i + 1
        self.assertEqual(functionals.compose(inc)(3), 4)
        self.assertEqual(functionals.compose(str, inc)(3), '4')

    def test_compose_repr(self):

        class Foo:
            pass

        func = functionals.compose(print, partial(Foo))
        pattern = r'<Composer at 0x.* of: print, .*partial.*Foo.*>'
        self.assertRegex(repr(func), pattern)
        self.assertRegex(str(func), pattern)


if __name__ == '__main__':
    unittest.main()
