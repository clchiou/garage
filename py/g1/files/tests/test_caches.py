import unittest

import tempfile
from pathlib import Path

from g1.files import caches


class CacheTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self._test_dir_tempdir = tempfile.TemporaryDirectory()
        self.test_dir_path = Path(self._test_dir_tempdir.name)

    def tearDown(self):
        self._test_dir_tempdir.cleanup()
        super().tearDown()

    def assert_cache_dir(self, entries):
        self.assertEqual(
            {
                path.relative_to(self.test_dir_path): path.read_bytes()
                for dir_path in self.test_dir_path.iterdir()
                for path in dir_path.iterdir()
            },
            {
                caches.Cache._get_relpath(key): value
                for key, value in entries.items()
            },
        )

    def assert_access_log(self, cache, access_log):
        self.assertEqual(
            list(cache._access_log.items()),
            [(cache._get_path(key), count) for key, count in access_log],
        )
        get_recency = cache._make_get_recency()
        for recency, (key, _) in enumerate(access_log):
            self.assertEqual(get_recency(cache._get_path(key)), recency)
        self.assertEqual(get_recency(Path('no-such-key')), len(access_log))

    def test_init(self):
        dir_path = self.test_dir_path / '00'
        dir_path.mkdir()
        for i in range(10):
            path = self.test_dir_path / ('00/%030d' % i)
            path.touch()
            with self.subTest(i):
                cache = caches.Cache(self.test_dir_path, 10)
                # No eviction yet.
                self.assertEqual(cache._eviction_countdown, 10 - i - 1)
                self.assertEqual(len(list(dir_path.iterdir())), i + 1)

    def test_init_with_eviction(self):
        dir_path = self.test_dir_path / '00'
        dir_path.mkdir()
        for i in range(20):
            path = self.test_dir_path / ('00/%030d' % i)
            path.touch()
        cache = caches.Cache(self.test_dir_path, 10)
        # __init__ evicts.
        self.assertEqual(cache._eviction_countdown, 2)
        self.assertEqual(len(list(dir_path.iterdir())), 8)

    def test_init_invalid_args(self):
        with self.assertRaisesRegex(AssertionError, r'expect.*is_dir'):
            caches.Cache(self.test_dir_path / 'foo', 100)
        with self.assertRaisesRegex(AssertionError, r'expect x > 0, not -1'):
            caches.Cache(self.test_dir_path, -1)
        with self.assertRaisesRegex(
            AssertionError, r'expect 0 <= post_eviction_size <= 1, not 2'
        ):
            caches.Cache(self.test_dir_path, 1, post_eviction_size=2)
        with self.assertRaisesRegex(
            AssertionError, r'expect 0 <= post_eviction_size <= 1, not -1'
        ):
            caches.Cache(self.test_dir_path, 1, post_eviction_size=-1)

    def test_access_log(self):
        cache = caches.Cache(self.test_dir_path, 100)
        self.assert_access_log(cache, [])

        cache.set(b'0', b'0')
        self.assert_access_log(cache, [(b'0', 1)])
        cache.set(b'1', b'1')
        self.assert_access_log(cache, [(b'1', 1), (b'0', 1)])
        cache.set(b'2', b'2')
        self.assert_access_log(cache, [(b'2', 1), (b'1', 1), (b'0', 1)])

        cache.set(b'0', b'4')
        self.assert_access_log(cache, [(b'0', 2), (b'2', 1), (b'1', 1)])
        self.assertEqual(cache.get(b'0'), b'4')
        self.assert_access_log(cache, [(b'0', 3), (b'2', 1), (b'1', 1)])
        self.assertEqual(cache.get(b'1'), b'1')
        self.assert_access_log(cache, [(b'1', 2), (b'0', 3), (b'2', 1)])
        self.assertEqual(cache.get(b'1'), b'1')
        self.assert_access_log(cache, [(b'1', 3), (b'0', 3), (b'2', 1)])

        self.assertIsNone(cache.get(b'4'))
        self.assert_access_log(cache, [(b'1', 3), (b'0', 3), (b'2', 1)])

    def test_estimate_size(self):
        cache = caches.Cache(self.test_dir_path, 100)
        self.assertEqual(cache.estimate_size(), 0)
        self.assert_cache_dir({})
        cache.set(b'0', b'')
        self.assertEqual(cache.estimate_size(), 1)
        self.assert_cache_dir({b'0': b''})
        cache.set(b'1', b'')
        self.assertEqual(cache.estimate_size(), 2)
        self.assert_cache_dir({b'0': b'', b'1': b''})
        cache.set(b'2', b'')
        self.assertEqual(cache.estimate_size(), 3)
        self.assert_cache_dir({b'0': b'', b'1': b'', b'2': b''})

    def test_evict(self):
        cache = caches.Cache(self.test_dir_path, 10)
        dir_path = self.test_dir_path / '00'
        dir_path.mkdir()
        for i in range(10):
            path = self.test_dir_path / ('00/%030d' % i)
            path.touch()
            cache._access_log[path] = 1
        self.assertEqual(len(list(dir_path.iterdir())), 10)
        self.assertEqual(len(cache._access_log), 10)

        self.assertEqual(cache.evict(), 2)
        self.assertEqual(len(list(dir_path.iterdir())), 8)
        self.assertEqual(len(cache._access_log), 8)
        self.assertEqual(cache._eviction_countdown, 2)

        for i in range(10, 20):
            path = self.test_dir_path / ('00/%030d' % i)
            path.touch()
            cache._access_log[path] = 1
        self.assertEqual(len(list(dir_path.iterdir())), 18)
        self.assertEqual(len(cache._access_log), 18)

        self.assertEqual(cache.evict(), 10)
        self.assertEqual(len(list(dir_path.iterdir())), 8)
        self.assertEqual(len(cache._access_log), 8)
        self.assertEqual(cache._eviction_countdown, 2)

    def test_evict_full(self):
        cache = caches.Cache(self.test_dir_path, 10, post_eviction_size=0)
        dir_path = self.test_dir_path / '00'
        dir_path.mkdir()
        for i in range(10):
            path = self.test_dir_path / ('00/%030d' % i)
            path.touch()
            cache._access_log[path] = 1
        self.assertEqual(len(list(dir_path.iterdir())), 10)
        self.assertEqual(len(cache._access_log), 10)

        self.assertEqual(cache.evict(), 10)
        self.assertFalse(dir_path.exists())
        self.assertEqual(len(cache._access_log), 0)
        self.assertEqual(cache._eviction_countdown, 10)

    def test_evict_order(self):
        cache = caches.Cache(self.test_dir_path, 10)
        dir_path = self.test_dir_path / '00'
        dir_path.mkdir()
        for i in range(10):
            path = self.test_dir_path / ('00/%030d' % i)
            path.touch()
            cache._log_access(path)
        self.assertEqual(len(list(dir_path.iterdir())), 10)
        self.assertEqual(len(cache._access_log), 10)

        get_recency = cache._make_get_recency()
        self.assertEqual(cache._evict_dir(dir_path, 8, get_recency), 2)
        self.assertEqual(
            sorted(dir_path.iterdir()),
            [self.test_dir_path / ('00/%030d' % i) for i in range(2, 10)],
        )
        self.assertEqual(
            sorted(cache._access_log),
            [self.test_dir_path / ('00/%030d' % i) for i in range(2, 10)],
        )

        get_recency = cache._make_get_recency()
        self.assertEqual(cache._evict_dir(dir_path, 0, get_recency), 8)
        self.assertFalse(dir_path.exists())
        self.assertEqual(cache._access_log, {})

    def test_get_file(self):
        cache = caches.Cache(self.test_dir_path, 10)
        cache.set(b'some key', b'some value')

        f, size = cache.get_file(b'some key')
        with f:
            self.assertTrue(Path(f.name).exists())
            self.assertEqual(f.read(), b'some value')
        self.assertEqual(size, 10)

        f, size = cache.get_file(b'some key')
        with f:
            cache.pop(b'some key')
            self.assertFalse(Path(f.name).exists())
            self.assertEqual(f.read(), b'some value')
        self.assertEqual(size, 10)

        self.assertIsNone(cache.get_file(b'some key'))

    def test_set(self):
        cache = caches.Cache(self.test_dir_path, 10)
        self.assert_access_log(cache, [])
        self.assertEqual(cache._eviction_countdown, 10)

        for i in range(10):
            cache.set(b'%d' % i, b'%d' % i)
            self.assert_cache_dir({b'%d' % j: b'%d' % j for j in range(i + 1)})
            self.assert_access_log(
                cache,
                [(b'%d' % j, 1) for j in reversed(range(i + 1))],
            )
            self.assertEqual(cache._eviction_countdown, 10 - i - 1)

        self.assert_cache_dir({b'%d' % i: b'%d' % i for i in range(10)})
        self.assert_access_log(
            cache,
            [(b'%d' % i, 1) for i in reversed(range(10))],
        )
        self.assertEqual(cache._eviction_countdown, 0)

        cache.set(b'10', b'10')
        # Cache over-evicted because post_eviction_size is much less
        # than 256.
        self.assert_access_log(cache, [])
        self.assertEqual(cache._eviction_countdown, 10)
        self.assertEqual(len(list(self.test_dir_path.iterdir())), 0)

    def test_setting_file(self):
        cache = caches.Cache(self.test_dir_path, 10)

        with cache.setting_file(b'some key') as value_file:
            self.assertFalse(cache._lock.locked())
            value_file.write(b'some value')

        self.assertEqual(cache.get(b'some key'), b'some value')

    def test_pop(self):
        cache = caches.Cache(self.test_dir_path, 10)
        with self.assertRaises(KeyError):
            cache.pop(b'0')
        self.assertIsNone(cache.pop(b'0', None))

        cache.set(b'0', b'0')
        self.assert_access_log(cache, [(b'0', 1)])
        self.assertEqual(cache._eviction_countdown, 9)
        self.assertEqual(len(list(self.test_dir_path.iterdir())), 1)

        self.assertEqual(cache.pop(b'0'), b'0')
        self.assert_access_log(cache, [])
        self.assertEqual(cache._eviction_countdown, 10)
        self.assertEqual(len(list(self.test_dir_path.iterdir())), 0)


if __name__ == '__main__':
    unittest.main()
