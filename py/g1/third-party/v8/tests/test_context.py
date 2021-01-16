import unittest

import contextlib

import v8


class ContextTest(unittest.TestCase):

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

    def test_context(self):
        with v8.Context(self.isolate) as context:
            self.assertEqual(len(context), 0)

            v8.run(context, 'x = 1; y = \'Hello, World!\'; z = true;')
            self.assertEqual(len(context), 3)
            self.assertEqual(list(context), ['x', 'y', 'z'])
            for name, expect in [
                ('x', 1),
                ('y', 'Hello, World!'),
                ('z', True),
            ]:
                with self.subTest(name):
                    self.assertIn(name, context)
                    self.assertEqual(context[name], expect)

            context['p'] = 0
            context['x'] = None
            self.assertEqual(len(context), 4)
            self.assertIn('p', context)
            self.assertEqual(context['p'], 0)
            self.assertIsNone(context['x'])

            # What does re-entering v8::Context actually do?
            with context:
                v8.run(context, 'a = 3.5;')
                self.assertEqual(len(context), 5)
            self.assertEqual(len(context), 5)

        self.assertEqual(len(context), 5)


if __name__ == '__main__':
    unittest.main()
