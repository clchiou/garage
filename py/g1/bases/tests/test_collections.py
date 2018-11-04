import unittest

from g1.bases import collections


class CollectionsTest(unittest.TestCase):

    def test_multiset(self):
        ms = collections.Multiset('abacc')

        for _ in range(3):
            ms.discard('d')
            self.assertTrue(ms)
            self.assertEqual(sorted(ms), ['a', 'a', 'b', 'c', 'c'])
            self.assertEqual(len(ms), 5)
            self.assertIn('a', ms)
            self.assertIn('b', ms)
            self.assertIn('c', ms)
            self.assertNotIn('d', ms)

        ms.discard('a')
        self.assertTrue(ms)
        self.assertEqual(sorted(ms), ['a', 'b', 'c', 'c'])
        self.assertEqual(len(ms), 4)
        self.assertIn('a', ms)
        self.assertIn('b', ms)
        self.assertIn('c', ms)
        self.assertNotIn('d', ms)

        for _ in range(3):
            ms.discard('a')
            self.assertTrue(ms)
            self.assertEqual(sorted(ms), ['b', 'c', 'c'])
            self.assertEqual(len(ms), 3)
            self.assertNotIn('a', ms)
            self.assertIn('b', ms)
            self.assertIn('c', ms)
            self.assertNotIn('d', ms)

        ms.discard('c')
        self.assertTrue(ms)
        self.assertEqual(sorted(ms), ['b', 'c'])
        self.assertEqual(len(ms), 2)
        self.assertNotIn('a', ms)
        self.assertIn('b', ms)
        self.assertIn('c', ms)
        self.assertNotIn('d', ms)

        for _ in range(3):
            ms.discard('c')
            self.assertTrue(ms)
            self.assertEqual(sorted(ms), ['b'])
            self.assertEqual(len(ms), 1)
            self.assertNotIn('a', ms)
            self.assertIn('b', ms)
            self.assertNotIn('c', ms)
            self.assertNotIn('d', ms)

        for _ in range(3):
            ms.discard('b')
            self.assertFalse(ms)
            self.assertEqual(sorted(ms), [])
            self.assertEqual(len(ms), 0)
            self.assertNotIn('a', ms)
            self.assertNotIn('b', ms)
            self.assertNotIn('c', ms)
            self.assertNotIn('d', ms)

    def test_namespace(self):

        ns = collections.Namespace('a', 'b', 'c')
        for name in ('a', 'b', 'c'):
            self.assertEqual(getattr(ns, name), name)
            self.assertEqual(ns[name], name)
        with self.assertRaises(AttributeError):
            getattr(ns, 'd')
        with self.assertRaises(KeyError):
            ns['d']  # pylint: disable=pointless-statement
        with self.assertRaises(TypeError):
            ns.d = 1
        self.assertEqual(tuple(ns), ('a', 'b', 'c'))
        self.assertEqual(ns._asdict(), {'a': 'a', 'b': 'b', 'c': 'c'})

        expect = {'a': 1, 'b': 2, 'c': 3}
        ns = collections.Namespace(**expect)
        for name, value in expect.items():
            self.assertEqual(getattr(ns, name), value)
            self.assertEqual(ns[name], value)
        with self.assertRaises(AttributeError):
            getattr(ns, 'd')
        with self.assertRaises(KeyError):
            ns['d']  # pylint: disable=pointless-statement
        with self.assertRaises(TypeError):
            ns.d = 1
        self.assertEqual(tuple(ns), ('a', 'b', 'c'))
        self.assertEqual(ns._asdict(), {'a': 1, 'b': 2, 'c': 3})

        ns = collections.Namespace()
        self.assertEqual(tuple(ns), ())

        with self.assertRaisesRegex(ValueError, r'overwrite'):
            collections.Namespace('a', a=1)
        with self.assertRaisesRegex(ValueError, r'starts with \'_\''):
            collections.Namespace('_a')
        with self.assertRaisesRegex(ValueError, r'starts with \'_\''):
            collections.Namespace(_a=1)


if __name__ == '__main__':
    unittest.main()
