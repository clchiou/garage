import unittest
import unittest.mock

import itertools

from g1.databases import caches


class CacheTest(unittest.TestCase):

    def assert_rows(self, cache, rows):
        with cache._engine.connect() as conn:
            self.assertEqual(list(conn.execute(cache._table.select())), rows)

    def assert_stats(self, cache, num_hits, num_misses):
        self.assertEqual(
            cache.get_stats(),
            caches.Cache.Stats(num_hits=num_hits, num_misses=num_misses),
        )

    @unittest.mock.patch.object(caches, 'time')
    def test_cache(self, mock_time):
        mock_time.monotonic_ns.side_effect = itertools.count(1000)

        cache = caches.Cache(10, post_eviction_size=8)
        self.assert_rows(cache, [])
        self.assert_stats(cache, 0, 0)

        self.assertIsNone(cache.get('hello'))
        self.assert_rows(cache, [])
        self.assert_stats(cache, 0, 1)

        cache.set('hello', b'world')
        self.assert_rows(cache, [('hello', b'world', 1000)])
        self.assert_stats(cache, 0, 1)

        self.assertEqual(cache.get('hello'), b'world')
        self.assert_rows(cache, [('hello', b'world', 1001)])
        self.assert_stats(cache, 1, 1)
        self.assertEqual(cache.get('hello'), b'world')
        self.assert_rows(cache, [('hello', b'world', 1002)])
        self.assert_stats(cache, 2, 1)

        cache.set('hello', b'spam')
        self.assert_rows(cache, [('hello', b'spam', 1003)])
        self.assert_stats(cache, 2, 1)
        cache.set('hello', b'spam')
        self.assert_rows(cache, [('hello', b'spam', 1004)])
        self.assert_stats(cache, 2, 1)

        cache.set('x', b'x')
        cache.set('y', b'y')
        self.assertEqual(cache.pop('hello'), b'spam')
        self.assert_rows(cache, [('x', b'x', 1005), ('y', b'y', 1006)])
        self.assert_stats(cache, 2, 1)

        with self.assertRaisesRegex(KeyError, 'no-such-key'):
            cache.pop('no-such-key')
        self.assertEqual(cache.pop('no-such-key', b'POP'), b'POP')
        self.assert_rows(cache, [('x', b'x', 1005), ('y', b'y', 1006)])
        self.assert_stats(cache, 2, 1)

    @unittest.mock.patch.object(caches, 'time')
    def test_evict(self, mock_time):
        mock_time.monotonic_ns.side_effect = itertools.count(1000)

        cache = caches.Cache(10, post_eviction_size=8)
        for i in range(10):
            cache.set('%d' % i, b'%d' % i)
        self.assertEqual(cache.get_size(), 10)
        self.assert_rows(
            cache,
            [('%d' % i, b'%d' % i, 1000 + i) for i in range(10)],
        )

        cache.set('9', b'test')  # No eviction.
        self.assertEqual(cache.get_size(), 10)
        self.assert_rows(
            cache,
            [('%d' % i, b'%d' % i, 1000 + i) for i in range(9)] + \
            [('9', b'test', 1010)],
        )

        cache.set('10', b'10')  # An eviction is triggered.
        self.assertEqual(cache.get_size(), 8)
        self.assert_rows(
            cache,
            [('%d' % i, b'%d' % i, 1000 + i) for i in range(3, 9)] + \
            [('9', b'test', 1010), ('10', b'10', 1011)],
        )

    @unittest.mock.patch.object(caches, 'time')
    def test_full_evict(self, mock_time):
        mock_time.monotonic_ns.side_effect = itertools.count(1000)

        cache = caches.Cache(10, post_eviction_size=0)
        for i in range(10):
            cache.set('%d' % i, b'%d' % i)
        self.assertEqual(cache.get_size(), 10)
        self.assert_rows(
            cache,
            [('%d' % i, b'%d' % i, 1000 + i) for i in range(10)],
        )

        cache.set('10', b'10')  # An eviction is triggered.
        self.assertEqual(cache.get_size(), 1)
        self.assert_rows(
            cache,
            [('10', b'10', 1010)],
        )

        self.assertEqual(cache.evict(), 1)
        self.assertEqual(cache.get_size(), 0)
        self.assert_rows(cache, [])

    @unittest.mock.patch.object(caches, 'time')
    def test_evict_manually(self, mock_time):
        mock_time.monotonic_ns.side_effect = itertools.count(1000)

        cache = caches.Cache(10, post_eviction_size=5)
        for i in range(8):
            cache.set('%d' % i, b'%d' % i)
        self.assertEqual(cache.get_size(), 8)
        self.assert_rows(
            cache,
            [('%d' % i, b'%d' % i, 1000 + i) for i in range(8)],
        )

        self.assertEqual(cache.evict(), 3)
        self.assertEqual(cache.get_size(), 5)
        self.assert_rows(
            cache,
            [('%d' % i, b'%d' % i, 1000 + i) for i in range(3, 8)],
        )


if __name__ == '__main__':
    unittest.main()
