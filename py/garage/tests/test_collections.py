import unittest

import typing

from garage.collections import *


class CollectionsTest(unittest.TestCase):

    def test_bidict(self):
        bidict = BiDict()
        self.assertFalse(bidict)
        self.assertFalse(bidict.inverse)

        bidict['x'] = 1
        self.assertIn(1, bidict.inverse)
        self.assertNotIn(2, bidict.inverse)
        self.assertEqual({1: 'x'}, dict(bidict.inverse))

        bidict['x'] = 2
        self.assertNotIn(1, bidict.inverse)
        self.assertIn(2, bidict.inverse)
        self.assertEqual({2: 'x'}, dict(bidict.inverse))

        self.assertTrue(bidict)
        self.assertTrue(bidict.inverse)

    def test_loading_dict(self):
        ldict = LoadingDict(lambda key: key)
        self.assertDictEqual({}, ldict.data)
        self.assertEqual('k1', ldict['k1'])
        ldict['k2'] = 'value'
        self.assertEqual('value', ldict['k2'])
        self.assertDictEqual({'k1': 'k1', 'k2': 'value'}, ldict.data)

    def test_dict_builder_write_in_place(self):
        data = {}
        DictBuilder(data).setitem('x', 1)
        self.assertEqual({'x': 1}, data)

    def test_dict_builder_if_elif_else(self):
        self.assertEqual(
            {'w': 1, 'x': 2, 'y': 3, 'z': 4},
            (DictBuilder()
             # w
             .if_(True)   .setitem('w', 1)
             .elif_(True) .setitem('w', 2)
             .elif_(True) .setitem('w', 3)
             .else_()     .setitem('w', 4)
             .end()
             # x
             .if_(False)  .setitem('x', 1)
             .elif_(True) .setitem('x', 2)
             .elif_(True) .setitem('x', 3)
             .else_()     .setitem('x', 4)
             .end()
             # y
             .if_(False)  .setitem('y', 1)
             .elif_(False).setitem('y', 2)
             .elif_(True) .setitem('y', 3)
             .else_()     .setitem('y', 4)
             .end()
             # z
             .if_(False)  .setitem('z', 1)
             .elif_(False).setitem('z', 2)
             .elif_(False).setitem('z', 3)
             .else_()     .setitem('z', 4)
             .end()
             .dict),
        )

        with self.assertRaises(AssertionError):
            DictBuilder().elif_(True)
        with self.assertRaises(AssertionError):
            DictBuilder().else_()
        with self.assertRaises(AssertionError):
            DictBuilder().end()

        with self.assertRaises(AssertionError):
            DictBuilder().if_(True).if_(True)
        with self.assertRaises(AssertionError):
            DictBuilder().if_(True).elif_(True).if_(True)
        with self.assertRaises(AssertionError):
            DictBuilder().if_(True).else_().elif_(True)

    def test_lru_cache(self):
        cache = LruCache(2)
        cache['a'] = 1
        cache['b'] = 2
        self.assertEqual([('a', 1), ('b', 2)], list(cache._cache.items()))
        cache['c'] = 3  # 'a' should be evicted.
        self.assertEqual([('b', 2), ('c', 3)], list(cache._cache.items()))
        self.assertEqual(2, cache['b']) # 'b' should be moved to last.
        self.assertEqual([('c', 3), ('b', 2)], list(cache._cache.items()))
        cache['d'] = 4  # 'c' should be evicted.
        self.assertEqual([('b', 2), ('d', 4)], list(cache._cache.items()))

    # Use new annotation syntax available since Python 3.6
    def test_named_tuple(self):

        class Mixin:
            def func(self):
                pass

        with self.assertRaisesRegex(ValueError, r'starts with underscore'):
            class Foo(NamedTuple):
                _x: int

        with self.assertRaisesRegex(TypeError, r'non-default .* after'):
            class Foo(NamedTuple):
                x: int = 1
                y: int

        class Foo(Mixin, NamedTuple):
            x: int
            y: int = 1

        # typing.NamedTuple drops all other base classes
        class Foo2(Mixin, typing.NamedTuple):
            x: int
            y: int = 1

        class Foo3(NamedTuple):
            x: object

        self.assertTrue(hasattr(Foo, 'func'))
        self.assertEqual((Mixin, NamedTuple), Foo.__bases__)
        self.assertFalse(hasattr(Foo2, 'func'))
        self.assertEqual((tuple,), Foo2.__bases__)

        self.assertEqual((42, 1), Foo(42))
        self.assertEqual((42, 1), Foo(x=42))
        self.assertEqual((42, 37), Foo(x=42, y=37))

        foo = Foo(42)
        self.assertTrue(isinstance(foo, Foo))
        self.assertTrue(isinstance(foo, tuple))

        self.assertEqual('Foo(x=42, y=1)', repr(foo))

        self.assertEqual((7, 8), Foo._make([7, 8]))

        self.assertEqual((42, 99), foo._replace(y=99))

        self.assertEqual({'x': 42, 'y': 1}, dict(foo._asdict()))

        self.assertEqual(
            {'x': ((), ())},
            dict(Foo3(x=((), ()))._asdict()),
        )

    def test_named_tuple_inheritance(self):

        class Mixin1:

            def func_mixin1(self):
                return 'mixin1'

            def func(self):
                return 'mixin1'

        class Mixin2:

            def func_mixin2(self):
                return 'mixin2'

            def func(self):
                return 'mixin2'

        class Base(Mixin1, NamedTuple):

            w: int = 1
            x: int = 2

            def func1(self):
                return 'base'

        class Derived(Mixin2, Base):

            y: int = 3
            z: int = 4

            def func2(self):
                return 'derived'

        self.assertEqual(['w', 'x'], list(Base._fields))
        self.assertEqual(['w', 'x', 'y', 'z'], list(Derived._fields))

        self.assertEqual((1, 2, 3, 4), Derived())
        self.assertEqual((4, 3, 2, 1), Derived(4, 3, 2, 1))

        b = Base()
        self.assertEqual('mixin1', b.func())
        self.assertEqual('base', b.func1())
        self.assertFalse(hasattr(b, 'func2'))
        self.assertEqual('mixin1', b.func_mixin1())
        self.assertFalse(hasattr(b, 'func_mixin2'))

        d = Derived()
        self.assertEqual('mixin2', d.func())
        self.assertEqual('base', d.func1())
        self.assertEqual('derived', d.func2())
        self.assertEqual('mixin1', d.func_mixin1())
        self.assertEqual('mixin2', d.func_mixin2())

        with self.assertRaisesRegex(TypeError, r'multiple .* bases'):
            class Derived2(Base, Derived):
                pass

        with self.assertRaisesRegex(ValueError, r'duplicated field name'):
            class Derived3(Base):
                w: int

    def test_singleton_meta(self):

        xs = []

        class Foo(metaclass=SingletonMeta):

            def __init__(self, x):
                xs.append(x)

        f1 = Foo(1)
        f2 = Foo(2)
        self.assertIs(f1, f2)
        self.assertEqual([1], xs)

    def test_symbols(self):
        symbols = Symbols('a', 'b', ('c', 3), d=4)
        self.assertEqual('a', symbols.a)
        self.assertEqual('b', symbols.b)
        self.assertEqual(3, symbols.c)
        self.assertEqual(4, symbols.d)
        with self.assertRaises(AttributeError):
            symbols.e
        with self.assertRaises(TypeError):
            symbols.e = 1
        with self.assertRaises(TypeError):
            symbols.a = 1
        with self.assertRaises(ValueError):
            Symbols('a', a=1)
        # Symbols return names in sorted order.
        self.assertEqual(['a', 'b', 'c', 'd'], list(symbols))
        symbols = Symbols('b', 'd', 'a', 'c')
        self.assertEqual(['a', 'b', 'c', 'd'], list(symbols))

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


class CollectionsHelperTest(unittest.TestCase):

    def test_is_ordered(self):
        self.assertTrue(is_ordered([]))
        self.assertTrue(is_ordered([1]))
        self.assertTrue(is_ordered([1, 1]))
        self.assertTrue(is_ordered([1, 1, 1]))
        self.assertTrue(is_ordered([1, 2]))
        self.assertTrue(is_ordered([1, 2, 3]))

        self.assertFalse(is_ordered([2, 1]))
        self.assertFalse(is_ordered([1, 3, 2]))

        self.assertTrue(is_ordered([], strict=True))
        self.assertTrue(is_ordered([1], strict=True))
        self.assertTrue(is_ordered([1, 2], strict=True))
        self.assertTrue(is_ordered([1, 2, 3], strict=True))

        self.assertFalse(is_ordered([1, 1], strict=True))
        self.assertFalse(is_ordered([1, 1, 1], strict=True))
        self.assertFalse(is_ordered([2, 1], strict=True))
        self.assertFalse(is_ordered([1, 3, 2], strict=True))

    def test_unique(self):
        self.assertListEqual([], unique([]))
        self.assertListEqual([1], unique([1, 1, 1]))
        self.assertListEqual([1, 3, 2, 4], unique([1, 1, 3, 2, 3, 2, 4, 1]))

    def test_unique_by_key(self):
        self.assertListEqual([], unique([], key=lambda _: None))
        self.assertListEqual(
            ['a1', 'b2'],
            unique(['a1', 'b2', 'a2', 'b1'], key=lambda x: x[0]),
        )

    def test_group(self):
        self.assertListEqual([[3], [1], [2]], group([3, 1, 2]))
        self.assertListEqual(
            [[3, 3, 3], [1], [2, 2]], group([3, 1, 2, 3, 2, 3]))

    def test_collect(self):
        self.assertListEqual(
            [(3, [3]), (1, [1]), (2, [2])],
            list(collect([3, 1, 2]).items()),
        )
        self.assertListEqual(
            [(3, [3, 3, 3]), (1, [1]), (2, [2, 2])],
            list(collect([3, 1, 2, 3, 2, 3]).items()),
        )

    def test_collect_pairs(self):
        self.assertListEqual(
            [('a', ['a', 'b', 'c']), ('b', ['d'])],
            list(collect_pairs(['aa', 'bd', 'ab', 'ac']).items()),
        )


if __name__ == '__main__':
    unittest.main()
