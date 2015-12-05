import unittest

from . import v8


class ContextTest(unittest.TestCase):

    def test_context(self):

        with v8.isolate() as isolate:

            with isolate.context() as context:
                self.assertEqual(
                    'hello world', context.evaluate('"hello " + "world"'))
                self.assertEqual(
                    [[[1, 2, 3]]], context.evaluate('[[[1, 2, 3]]]'))

            with isolate.context() as context:
                context.execute('''
                purpose = 42;
                pi = 3.14159;
                dict = {1: {}, 'x': {}}
                ''')

                purpose = context['purpose']
                self.assertTrue(isinstance(purpose, int))
                self.assertEqual(42, purpose)

                self.assertEqual(3.14159, context['pi'])

                self.assertEqual({1: {}, 'x': {}}, context['dict'])

                self.assertSetEqual(
                    {'purpose', 'pi', 'dict'},
                    set(context),
                )

                for name in ('purpose', 'pi', 'dict'):
                    self.assertIn(name, context)

                self.assertIsNone(context.get('no_such_thing'))
                with self.assertRaises(KeyError):
                    context['no_such_thing']

                self.assertDictEqual(
                    {
                        'purpose': 42,
                        'pi': 3.14159,
                        'dict': {1: {}, 'x': {}},
                    },
                    dict(context),
                )


if __name__ == '__main__':
    unittest.main()
