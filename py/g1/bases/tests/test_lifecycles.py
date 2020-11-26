import unittest

import gc

from g1.bases import lifecycles


class LifecyclesTest(unittest.TestCase):

    def test_alive_object_counter(self):
        c = lifecycles.AliveObjectCounter()
        self.assertEqual(c.take_snapshot(), {})

        with self.assertRaisesRegex(
            TypeError,
            r'cannot create weak reference to \'object\' object',
        ):
            c.monitor_object_aliveness(object())
        self.assertEqual(c.take_snapshot(), {})

        o1 = Foo()
        c.monitor_object_aliveness(o1)
        self.assertEqual(c.take_snapshot(), {Foo: 1})

        del o1
        gc.collect()  # Ensure that ``o1`` is recycled.
        self.assertEqual(c.take_snapshot(), {Foo: 0})

        o2 = Foo()
        c.monitor_object_aliveness(o2, (Foo, 'x'))
        self.assertEqual(c.take_snapshot(), {Foo: 0, (Foo, 'x'): 1})

        # Sadly we do not detect duplication at the moment.
        c.monitor_object_aliveness(o2, (Foo, 'x'))
        self.assertEqual(c.take_snapshot(), {Foo: 0, (Foo, 'x'): 2})

        del o2
        gc.collect()  # Ensure that ``o2`` is recycled.
        self.assertEqual(c.take_snapshot(), {Foo: 0, (Foo, 'x'): 0})

        c.add_to('x', 3)
        self.assertEqual(c.take_snapshot(), {Foo: 0, (Foo, 'x'): 0, 'x': 3})


class Foo:
    pass


if __name__ == '__main__':
    unittest.main()
