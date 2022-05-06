import unittest

import operator
from collections import abc

from g1.bases.collections import (
    LoadingDict,
    LruCache,
    Multiset,
    Namespace,
)


class LoadingDictTest(unittest.TestCase):

    def test_loading_dict(self):

        ks = []

        def load(key):
            if key == 'no-such-key':
                raise KeyError(key)
            ks.append(key)
            return key

        d = LoadingDict(load, p=1, q=2)
        self.assertEqual(d, {'p': 1, 'q': 2})
        self.assertEqual(ks, [])

        for _ in range(3):
            self.assertEqual(d['x'], 'x')
            self.assertEqual(d['y'], 'y')

        self.assertEqual(d, {'p': 1, 'q': 2, 'x': 'x', 'y': 'y'})
        self.assertEqual(ks, ['x', 'y'])

        with self.assertRaises(KeyError):
            d['no-such-key']  # pylint: disable=pointless-statement
        self.assertIsNone(d.get('no-such-key'))

        self.assertEqual(d, {'p': 1, 'q': 2, 'x': 'x', 'y': 'y'})
        self.assertEqual(ks, ['x', 'y'])


class LruCacheTest(unittest.TestCase):

    def assert_cache(self, actual, expect):
        self.assertEqual(list(actual._cache.items()), expect)

    def test_lru_cache(self):

        cache = LruCache(2)
        cache['a'] = 1
        cache['b'] = 2
        self.assert_cache(cache, [('a', 1), ('b', 2)])

        with self.assertRaises(KeyError):
            cache['x']  # pylint: disable=pointless-statement
        self.assert_cache(cache, [('a', 1), ('b', 2)])

        self.assertIsNone(cache.get('x'))
        self.assert_cache(cache, [('a', 1), ('b', 2)])

        cache['c'] = 3  # 'a' should be evicted.
        self.assert_cache(cache, [('b', 2), ('c', 3)])

        self.assertEqual(2, cache['b'])  # 'b' should be moved to last.
        self.assert_cache(cache, [('c', 3), ('b', 2)])

        cache['d'] = 4  # 'c' should be evicted.
        self.assert_cache(cache, [('b', 2), ('d', 4)])

        del cache['b']
        self.assert_cache(cache, [('d', 4)])

        cache['a'] = 1
        cache['b'] = 2
        self.assert_cache(cache, [('a', 1), ('b', 2)])

        with self.assertRaises(KeyError):
            del cache['x']
        self.assert_cache(cache, [('a', 1), ('b', 2)])

        with self.assertRaises(KeyError):
            cache.pop('x')
        self.assert_cache(cache, [('a', 1), ('b', 2)])

        self.assertEqual(('a', 1), cache.popitem())
        self.assert_cache(cache, [('b', 2)])

        cache['c'] = 3
        self.assert_cache(cache, [('b', 2), ('c', 3)])

        self.assertEqual(3, cache.pop('c'))
        self.assert_cache(cache, [('b', 2)])

        self.assertEqual(4, cache.setdefault('d', 4))
        self.assert_cache(cache, [('b', 2), ('d', 4)])

        self.assertEqual(2, cache.setdefault('b', 99))
        self.assert_cache(cache, [('d', 4), ('b', 2)])

        # Test ``__contains__``.
        self.assertTrue('d' in cache)
        self.assert_cache(cache, [('b', 2), ('d', 4)])

    def test_methods_operate_on_entire_cache(self):
        """Test methods that should not alter cache eviction order."""

        cache = LruCache(2)
        cache['a'] = 1
        cache['b'] = 2
        self.assert_cache(cache, [('a', 1), ('b', 2)])

        self.assertEqual(len(cache), 2)
        self.assert_cache(cache, [('a', 1), ('b', 2)])

        self.assertEqual(list(cache), ['a', 'b'])
        self.assert_cache(cache, [('a', 1), ('b', 2)])

        self.assertEqual(list(cache.keys()), ['a', 'b'])
        self.assert_cache(cache, [('a', 1), ('b', 2)])

        self.assertEqual(list(cache.items()), [('a', 1), ('b', 2)])
        self.assert_cache(cache, [('a', 1), ('b', 2)])

        self.assertEqual(list(cache.values()), [1, 2])
        self.assert_cache(cache, [('a', 1), ('b', 2)])


class MultisetTest(unittest.TestCase):

    def test_abc(self):
        self.assertTrue(Multiset, abc.MutableSet)

    def test_multiset(self):
        ms = Multiset('abacc')

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

    def test_copy(self):
        m1 = Multiset('aabccd')
        m2 = m1.copy()
        self.assertEqual(m1, m2)
        self.assertEqual(len(m1), len(m2))

    def test_comparators(self):
        self.assertTrue(Multiset('aab').isdisjoint(Multiset('cdd')))
        self.assertLess(Multiset('aa'), Multiset('aab'))
        self.assertLessEqual(Multiset('aab'), Multiset('aab'))
        self.assertEqual(Multiset('aab'), Multiset('aab'))
        self.assertEqual(Multiset('aabc'), Multiset('caba'))
        self.assertGreater(Multiset('aab'), Multiset('aa'))
        self.assertGreaterEqual(Multiset('aab'), Multiset('aab'))
        self.assertFalse(Multiset('aab') < Multiset('aac'))
        self.assertFalse(Multiset('aab') > Multiset('aac'))
        self.assertNotEqual(Multiset('aab'), Multiset('aac'))
        self.assertNotEqual(Multiset('aab'), Multiset('caa'))

    def test_operators(self):
        checks = [
            ('and', Multiset('aab'), Multiset('aac'), Multiset('aa')),
            ('or', Multiset('aab'), Multiset('aac'), Multiset('aabc')),
            ('xor', Multiset('aab'), Multiset('aac'), Multiset('bc')),
            ('xor', Multiset('aaab'), Multiset('aac'), Multiset('abc')),
            ('add', Multiset('aab'), Multiset('aac'), Multiset('aaaabc')),
            ('sub', Multiset('aab'), Multiset('aac'), Multiset('b')),
        ]
        for op, p, q, expect in checks:
            iop = 'i' + op
            if op in ('and', 'or'):
                op += '_'
            with self.subTest(check=op):
                self.assertEqual(getattr(operator, op)(p, q), expect)
            with self.subTest(check=iop):
                pp = p.copy()
                self.assertEqual(getattr(operator, iop)(pp, q), expect)
                self.assertEqual(pp, expect)

    def test_count(self):
        m = Multiset('aabcc')
        self.assertEqual(m.count('a'), 2)
        self.assertEqual(m.count('b'), 1)
        self.assertEqual(m.count('c'), 2)
        self.assertEqual(m.count('d'), 0)

    def test_remove(self):
        m = Multiset('aabcc')
        m.remove('a')
        self.assertEqual(m, Multiset('abcc'))
        with self.assertRaises(KeyError):
            m.remove('d')

    def test_pop(self):
        m = Multiset('aabcc')
        self.assertEqual(
            frozenset(m.pop() for _ in range(len(m))),
            frozenset('aabcc'),
        )
        with self.assertRaises(KeyError):
            m.pop()


class NamespaceTest(unittest.TestCase):

    def test_namespace(self):

        ns = Namespace('a', 'b', 'c')
        for name in ('a', 'b', 'c'):
            self.assertEqual(getattr(ns, name), name)
            self.assertIn(name, ns)
            self.assertEqual(ns[name], name)
        with self.assertRaises(AttributeError):
            getattr(ns, 'd')
        self.assertNotIn('d', ns)
        with self.assertRaises(KeyError):
            ns['d']  # pylint: disable=pointless-statement
        with self.assertRaises(TypeError):
            ns.d = 1
        self.assertEqual(tuple(ns), ('a', 'b', 'c'))
        self.assertEqual(ns._asdict(), {'a': 'a', 'b': 'b', 'c': 'c'})

        expect = {'a': 1, 'b': 2, 'c': 3}
        ns = Namespace(**expect)
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

        ns = Namespace()
        self.assertEqual(tuple(ns), ())

        with self.assertRaisesRegex(ValueError, r'overwrite'):
            Namespace('a', a=1)
        with self.assertRaisesRegex(ValueError, r'starts with \'_\''):
            Namespace('_a')
        with self.assertRaisesRegex(ValueError, r'starts with \'_\''):
            Namespace(_a=1)


if __name__ == '__main__':
    unittest.main()
