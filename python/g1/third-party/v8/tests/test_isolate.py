import unittest

import v8


class IsolateTest(unittest.TestCase):

    def test_num_alive(self):
        self.assertEqual(v8.Isolate.num_alive, 0)

        with v8.Isolate() as i1:
            self.assertEqual(v8.Isolate.num_alive, 1)

            with self.assertRaisesRegex(
                RuntimeError,
                r'this context manager only allows being entered once',
            ):
                i1.__enter__()
            self.assertEqual(v8.Isolate.num_alive, 1)

            with i1.scope():
                self.assertEqual(v8.Isolate.num_alive, 1)
                with i1.scope():
                    self.assertEqual(v8.Isolate.num_alive, 1)
                self.assertEqual(v8.Isolate.num_alive, 1)
            self.assertEqual(v8.Isolate.num_alive, 1)

            with v8.Isolate():
                self.assertEqual(v8.Isolate.num_alive, 2)

            self.assertEqual(v8.Isolate.num_alive, 1)

        self.assertEqual(v8.Isolate.num_alive, 0)

        with self.assertRaisesRegex(
            RuntimeError,
            r'this context manager only allows being entered once',
        ):
            i1.__enter__()
        self.assertEqual(v8.Isolate.num_alive, 0)


if __name__ == '__main__':
    unittest.main()
