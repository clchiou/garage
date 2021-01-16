import unittest

import contextlib

import v8


class ScriptTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.assertEqual(v8.Isolate.num_alive, 0)
        self.stack = contextlib.ExitStack()
        self.stack.__enter__()
        self.isolate = self.stack.enter_context(v8.Isolate())
        self.assertEqual(v8.Isolate.num_alive, 1)
        self.stack.enter_context(self.isolate.scope())
        self.stack.enter_context(v8.HandleScope(self.isolate))

    def tearDown(self):
        self.stack.close()
        self.assertEqual(v8.Isolate.num_alive, 0)
        super().tearDown()

    def test_syntax_error(self):
        context = self.stack.enter_context(v8.Context(self.isolate))
        with self.assertRaisesRegex(
            v8.JavaScriptError,
            r'SyntaxError: Invalid or unexpected token',
        ):
            v8.Script(context, '<test>', '#')

    def test_run(self):
        context = self.stack.enter_context(v8.Context(self.isolate))
        script = v8.Script(context, '<test>', '"Hello, World!";')
        self.assertEqual(script.run(context), 'Hello, World!')

    def test_throw(self):
        context = self.stack.enter_context(v8.Context(self.isolate))
        script = v8.Script(context, '<test>', 'throw "Hello, World!";')
        with self.assertRaisesRegex(v8.JavaScriptError, r'"Hello, World!"'):
            script.run(context)

    def test_multiple_contexts(self):
        with v8.Context(self.isolate) as c1:
            script = v8.Script(
                c1,
                '<test>',
                '''
                function f() {
                  return x;
                }
                f();
                ''',
            )
            with self.assertRaisesRegex(
                v8.JavaScriptError,
                r'ReferenceError: x is not defined',
            ):
                script.run(c1)

            c1['x'] = 'Hello, World!'
            self.assertEqual(script.run(c1), 'Hello, World!')

        # Run with another context.  It does not seem to matter.  Then
        # why does v8::Script::Run takes a v8::Context for argument?
        with v8.Context(self.isolate) as c2:
            self.assertEqual(script.run(c2), 'Hello, World!')


if __name__ == '__main__':
    unittest.main()
