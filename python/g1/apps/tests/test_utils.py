import unittest

import functools

from g1.apps import utils


class GetAnnotationsTest(unittest.TestCase):

    def test_get_annotations(self):

        class Test:

            def __init__(self, p: 'P'):
                pass

            def __call__(self, q: 'Q') -> 'R':
                pass

        def test(x: 'X') -> 'Y':
            del x  # Unused.

        for func, annotations in (
            (test, {
                'x': 'X',
                'return': 'Y',
            }),
            (Test, {
                'p': 'P',
            }),
            (Test(0), {
                'q': 'Q',
                'return': 'R',
            }),
            (functools.partial(test), {
                'x': 'X',
                'return': 'Y',
            }),
            (functools.partial(Test), {
                'p': 'P',
            }),
            (functools.partial(Test(0)), {
                'q': 'Q',
                'return': 'R',
            }),
        ):
            with self.subTest(func):
                self.assertEqual(utils.get_annotations(func), annotations)

        self.assertEqual(utils.get_annotations(test), test.__annotations__)

    def test_no_annotation(self):

        class Empty:

            def __init__(self, p):
                pass

            def __call__(self, q):
                pass

        def empty(x):
            del x  # Unused.

        for func in (
            empty,
            Empty,
            Empty(0),
            functools.partial(empty),
            functools.partial(Empty),
            functools.partial(Empty(0)),
        ):
            with self.subTest(func):
                self.assertEqual(utils.get_annotations(func), {})

        self.assertEqual(utils.get_annotations(empty), empty.__annotations__)


if __name__ == '__main__':
    unittest.main()
