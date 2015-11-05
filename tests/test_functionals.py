import unittest

from garage.functionals import *


class FunctionalsTest(unittest.TestCase):

    def test_run_once(self):
        logs = []
        def foo(i):
            logs.append(i)

        f = run_once(foo)
        for i in range(10):
            f(i)
        self.assertListEqual([0], logs)

    def test_with_defaults(self):

        def func(*args, **kwargs):
            return args, kwargs

        func2 = with_defaults(func, {'x': 1, 'y': 2})
        args, kwargs = func2('a', 'b', 'c', z=3)
        self.assertTupleEqual(('a', 'b', 'c'), args)
        self.assertDictEqual(dict(x=1, y=2, z=3), kwargs)


if __name__ == '__main__':
    unittest.main()
