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


if __name__ == '__main__':
    unittest.main()
