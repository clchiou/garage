import unittest

from g1.bases import contexts


class ContextTest(unittest.TestCase):

    def assert_context(self, context, expect):
        self.assertEqual(context._context, expect)
        self.assertEqual(context.asdict(), expect)
        for key, value in expect.items():
            self.assertEqual(context.get(key), value)
        self.assertIsNone(context.get('no-such-key'))

    def test_context(self):
        self.assert_context(contexts.Context({'y': 0}), {'y': 0})

        cxt = contexts.Context()
        child_1 = cxt.make({'x': 1})
        child_2 = cxt.make({'x': 2})
        grandchild = child_1.make({'x': 3}, allow_overwrite=True)
        self.assert_context(cxt, {})
        self.assert_context(child_1, {'x': 1})
        self.assert_context(child_2, {'x': 2})
        self.assert_context(grandchild, {'x': 3})

        with self.assertRaisesRegex(AssertionError, r'expect x.isdisjoint'):
            child_1.make({'x': 3})
        with self.assertRaisesRegex(AssertionError, r'expect \'x\' not in'):
            child_1.set('x', 3)
        self.assert_context(child_1, {'x': 1})

        child_1.set('x', 3, allow_overwrite=True)
        self.assert_context(child_1, {'x': 3})


if __name__ == '__main__':
    unittest.main()
