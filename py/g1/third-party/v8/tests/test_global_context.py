import unittest

import contextlib

import v8


class GlobalContextTest(unittest.TestCase):

    def test_no_re_enter(self):
        self.assertEqual(v8.Isolate.num_alive, 0)
        with v8.Isolate() as i1, i1.scope(), v8.HandleScope(i1):
            c1 = v8.Context(i1)

            with v8.GlobalContext(i1, c1) as global_context:
                with self.assertRaisesRegex(
                    RuntimeError,
                    r'this context manager only allows being entered once',
                ):
                    global_context.__enter__()

        with self.assertRaisesRegex(
            RuntimeError,
            r'this context manager only allows being entered once',
        ):
            global_context.__enter__()

        self.assertEqual(v8.Isolate.num_alive, 0)

    def test_context(self):
        with contextlib.ExitStack() as stack:
            isolate = stack.enter_context(v8.Isolate())
            stack.enter_context(isolate.scope())

            with v8.HandleScope(isolate):
                with v8.Context(isolate) as c1:
                    c1['x'] = 'foo bar'
                    global_context = stack.enter_context(
                        v8.GlobalContext(isolate, c1)
                    )
                    self.assertEqual(
                        global_context.get(isolate)['x'],
                        'foo bar',
                    )
                self.assertEqual(
                    global_context.get(isolate)['x'],
                    'foo bar',
                )

            # In another handle scope.
            with v8.HandleScope(isolate):
                self.assertEqual(
                    global_context.get(isolate)['x'],
                    'foo bar',
                )


if __name__ == '__main__':
    unittest.main()
