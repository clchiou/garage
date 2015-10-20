import unittest

from garage.collections import *


class CollectionsTest(unittest.TestCase):

    def test_loading_dict(self):
        ldict = LoadingDict(lambda key: key)
        self.assertDictEqual({}, ldict.data)
        self.assertEqual('k1', ldict['k1'])
        ldict['k2'] = 'value'
        self.assertEqual('value', ldict['k2'])
        self.assertDictEqual({'k1': 'k1', 'k2': 'value'}, ldict.data)

    def test_dict_as_attrs(self):
        attrs = DictViewNamespace({'y': 1})

        self.assertEqual(1, attrs.y)
        self.assertFalse(hasattr(attrs, 'x'))

        attrs.x = 2
        self.assertEqual(2, attrs.x)

        del attrs.y
        self.assertFalse(hasattr(attrs, 'y'))

        attrs.z = 3
        self.assertListEqual(['x', 'z'], list(sorted((attrs))))

    def test_trie(self):
        trie = Trie()
        self.assertTrieNodeEqual((Trie.EMPTY, {}), trie._root)
        with self.assertRaises(KeyError):
            trie['']
        with self.assertRaises(KeyError):
            trie['no-such-key']

        trie[''] = 'hello'
        self.assertTrieNodeEqual(
            ('hello', {}),
            trie._root,
        )

        trie['abc'] = 'world'
        self.assertTrieNodeEqual(
            ('hello', {
                'a': (Trie.EMPTY, {
                    'b': (Trie.EMPTY, {
                        'c': ('world', {}),
                    }),
                }),
            }),
            trie._root,
        )

        self.assertEqual('hello', trie.get('', exact=False))
        self.assertEqual('hello', trie.get('a', exact=False))
        self.assertEqual('hello', trie.get('ab', exact=False))
        self.assertEqual('world', trie.get('abc', exact=False))

        self.assertEqual('hello', trie.get('x', exact=False))
        self.assertEqual('hello', trie.get('ax', exact=False))
        self.assertEqual('hello', trie.get('abx', exact=False))
        self.assertEqual('world', trie.get('abcx', exact=False))

        self.assertListEqual([('', 'hello')], list(trie.get_values('')))
        self.assertListEqual([('', 'hello')], list(trie.get_values('a')))
        self.assertListEqual([('', 'hello')], list(trie.get_values('ab')))
        self.assertListEqual(
            [('', 'hello'), ('abc', 'world')], list(trie.get_values('abc')))
        self.assertListEqual(
            [('', 'hello'), ('abc', 'world')], list(trie.get_values('abcx')))

        trie['abd'] = 'spam'
        self.assertTrieNodeEqual(
            ('hello', {
                'a': (Trie.EMPTY, {
                    'b': (Trie.EMPTY, {
                        'c': ('world', {}),
                        'd': ('spam', {}),
                    }),
                }),
            }),
            trie._root,
        )

        trie['ae'] = 'egg'
        self.assertTrieNodeEqual(
            ('hello', {
                'a': (Trie.EMPTY, {
                    'b': (Trie.EMPTY, {
                        'c': ('world', {}),
                        'd': ('spam', {}),
                    }),
                    'e': ('egg', {})
                }),
            }),
            trie._root,
        )

        trie['abc'] = 'test'
        self.assertTrieNodeEqual(
            ('hello', {
                'a': (Trie.EMPTY, {
                    'b': (Trie.EMPTY, {
                        'c': ('test', {}),
                        'd': ('spam', {}),
                    }),
                    'e': ('egg', {})
                }),
            }),
            trie._root,
        )

        trie = Trie()
        trie['abc'] = 'test'
        for key in ('', 'a', 'ab'):
            for exact in (True, False):
                self.assertEqual(None, trie.get(key, exact=exact))
        self.assertEqual('test', trie.get('abc', exact=True))
        self.assertEqual('test', trie.get('abc', exact=False))
        self.assertEqual(None, trie.get('abcx', exact=True))
        self.assertEqual('test', trie.get('abcx', exact=False))
        self.assertListEqual([], list(trie.get_values('')))
        self.assertListEqual([], list(trie.get_values('a')))
        self.assertListEqual([], list(trie.get_values('ab')))
        self.assertListEqual([('abc', 'test')], list(trie.get_values('abc')))
        self.assertListEqual([('abc', 'test')], list(trie.get_values('abcx')))

    def test_trie_values(self):
        trie = Trie()
        trie[''] = 0
        trie['a'] = 1
        trie['ab'] = 2
        trie['abc'] = 3
        trie['b'] = 4
        trie['bc'] = 5
        self.assertListEqual([0, 1, 2, 3, 4, 5], list(trie.values()))

    def assertTrieNodeEqual(self, expact, node):
        value, children = expact
        self.assertEqual(value, node.value)
        self.assertSetEqual(set(children), set(node.children))
        for element in children:
            child = node.children[element]
            self.assertIs(node, child.parent)
            self.assertTrieNodeEqual(children[element], child)


if __name__ == '__main__':
    unittest.main()
