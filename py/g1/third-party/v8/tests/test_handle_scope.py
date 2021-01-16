import unittest

import v8


class HandleScopeTest(unittest.TestCase):

    def test_no_re_enter(self):
        self.assertEqual(v8.Isolate.num_alive, 0)
        with v8.Isolate() as i1, i1.scope():

            with v8.HandleScope(i1) as handle_scope:
                with self.assertRaisesRegex(
                    RuntimeError,
                    r'this context manager only allows being entered once',
                ):
                    handle_scope.__enter__()

        with self.assertRaisesRegex(
            RuntimeError,
            r'this context manager only allows being entered once',
        ):
            handle_scope.__enter__()

        self.assertEqual(v8.Isolate.num_alive, 0)


if __name__ == '__main__':
    unittest.main()
