import unittest
import unittest.mock

import itertools

from g1.bases import pools


class TimeoutPoolTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.mock_allocate = unittest.mock.Mock()
        self.mock_allocate.side_effect = itertools.count()
        self.mock_release = unittest.mock.Mock()
        self.pool = pools.TimeoutPool(4, self.mock_allocate, self.mock_release)

    def assert_pool(
        self,
        expect_pool,
        expect_num_allocations,
        expect_num_concurrent_resources,
        expect_max_concurrent_resources,
    ):
        self.assertEqual(list(self.pool._pool), expect_pool)
        stats = self.pool.get_stats()
        self.assertEqual(stats.num_allocations, expect_num_allocations)
        self.assertEqual(
            stats.num_concurrent_resources, expect_num_concurrent_resources
        )
        self.assertEqual(
            stats.max_concurrent_resources, expect_max_concurrent_resources
        )

    @unittest.mock.patch.object(pools, 'time')
    def test_pool_not_timed(self, mock_time):
        mock_time.monotonic.return_value = 1001

        self.assert_pool([], 0, 0, 0)
        for i in range(5):
            self.assertEqual(self.pool.get(), i)
            self.assert_pool([], i + 1, i + 1, i + 1)

        for i in reversed(range(1, 5)):
            self.pool.return_(i)
            self.assert_pool(
                [(j, 1001) for j in reversed(range(i, 5))],
                5,
                5,
                5,
            )
        self.pool.return_(0)
        self.assert_pool([(j, 1001) for j in reversed(range(4))], 5, 4, 5)

        self.pool.cleanup()
        self.assert_pool([(j, 1001) for j in reversed(range(4))], 5, 4, 5)

        self.pool.close()
        self.assert_pool([], 5, 0, 5)

        for i in range(5, 10):
            self.assertEqual(self.pool.get(), i)
            self.assert_pool([], i + 1, i - 4, 5)
        self.assertEqual(self.pool.get(), 10)
        self.assert_pool([], 11, 6, 6)

        self.assertEqual(len(self.mock_allocate.mock_calls), 11)
        self.mock_release.assert_has_calls([
            unittest.mock.call(i) for i in reversed(range(5))
        ])

    @unittest.mock.patch.object(pools, 'time')
    def test_timeout(self, mock_time):
        mock_monotonic = mock_time.monotonic
        self.assert_pool([], 0, 0, 0)

        for i in range(4):
            self.assertEqual(self.pool.get(), i)
        self.assert_pool([], 4, 4, 4)

        mock_monotonic.return_value = 1000
        self.pool.return_(0)
        self.assert_pool([(0, 1000)], 4, 4, 4)

        mock_monotonic.return_value = 1100
        self.pool.return_(1)
        self.assert_pool([(0, 1000), (1, 1100)], 4, 4, 4)

        mock_monotonic.return_value = 1200
        self.pool.return_(2)
        self.assert_pool([(0, 1000), (1, 1100), (2, 1200)], 4, 4, 4)

        mock_monotonic.return_value = 1300
        self.pool.return_(3)
        self.assert_pool([(0, 1000), (1, 1100), (2, 1200), (3, 1300)], 4, 4, 4)

        self.assertEqual(self.pool.get(), 3)
        self.assert_pool([(0, 1000), (1, 1100), (2, 1200)], 4, 4, 4)
        self.pool.return_(3)
        self.assert_pool([(0, 1000), (1, 1100), (2, 1200), (3, 1300)], 4, 4, 4)

        # Test `get` returning the most recently released resource.
        mock_monotonic.return_value = 1400
        self.assertEqual(self.pool.get(), 3)
        self.assert_pool([(1, 1100), (2, 1200)], 4, 3, 4)

        mock_monotonic.return_value = 1500
        self.pool.return_(3)
        self.assert_pool([(2, 1200), (3, 1500)], 4, 2, 4)

        mock_monotonic.return_value = 1600
        self.pool.cleanup()
        self.assert_pool([(3, 1500)], 4, 1, 4)

        self.assertEqual(len(self.mock_allocate.mock_calls), 4)
        self.mock_release.assert_has_calls([
            unittest.mock.call(0),
            unittest.mock.call(1),
            unittest.mock.call(2),
        ])

    @unittest.mock.patch.object(pools, 'time')
    def test_context(self, mock_time):
        mock_time.monotonic.return_value = 1001

        self.assert_pool([], 0, 0, 0)
        with self.pool:
            for i in range(4):
                self.assertEqual(self.pool.get(), i)
                self.assert_pool([], i + 1, i + 1, i + 1)
            for i in reversed(range(4)):
                self.pool.return_(i)
                self.assert_pool(
                    [(j, 1001) for j in reversed(range(i, 4))],
                    4,
                    4,
                    4,
                )
        self.assert_pool([], 4, 0, 4)

        self.assertEqual(len(self.mock_allocate.mock_calls), 4)
        self.mock_release.assert_has_calls([
            unittest.mock.call(i) for i in reversed(range(4))
        ])

    @unittest.mock.patch.object(pools, 'time')
    def test_using(self, mock_time):
        mock_time.monotonic.return_value = 1001

        self.assert_pool([], 0, 0, 0)
        with self.pool.using() as r0:
            self.assertEqual(r0, 0)
            self.assert_pool([], 1, 1, 1)
            with self.pool.using() as r1:
                self.assertEqual(r1, 1)
                self.assert_pool([], 2, 2, 2)
            self.assert_pool([(1, 1001)], 2, 2, 2)
        self.assert_pool([(1, 1001), (0, 1001)], 2, 2, 2)

        # Test `get` returning the most recently released resource.
        for _ in range(3):
            with self.pool.using() as r0:
                self.assertEqual(r0, 0)
                self.assert_pool([(1, 1001)], 2, 2, 2)
        self.assert_pool([(1, 1001), (0, 1001)], 2, 2, 2)

        self.assertEqual(len(self.mock_allocate.mock_calls), 2)
        self.mock_release.assert_not_called()


if __name__ == '__main__':
    unittest.main()
