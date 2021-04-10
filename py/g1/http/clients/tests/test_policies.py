import unittest
import unittest.mock

from g1.asyncs import kernels
from g1.http.clients import policies


class RateLimitTest(unittest.TestCase):

    def setUp(self):
        self.monotonic_mock = \
            unittest.mock.patch(policies.__name__ + '.time').start().monotonic
        mocked_timers = \
            unittest.mock.patch(policies.__name__ + '.timers').start()
        mocked_timers.sleep = mocked_sleep

    def tearDown(self):
        unittest.mock.patch.stopall()

    @kernels.with_kernel
    def test_unlimited(self):
        self.assertIsNone(kernels.run(policies.unlimited))

    @kernels.with_kernel
    def test_token_bucket(self):
        self.monotonic_mock.side_effect = [99]
        tb = policies.TokenBucket(0.5, 2, False)
        self.assertEqual(tb._num_tokens, 0)
        self.assertEqual(tb._last_added, 99)

        self.monotonic_mock.side_effect = [99, 99, 101]
        kernels.run(tb)
        self.assertEqual(tb._num_tokens, 0)
        self.assertEqual(tb._last_added, 101)

        self.monotonic_mock.side_effect = [101, 102, 105]
        kernels.run(tb)
        self.assertEqual(tb._num_tokens, 1)
        self.assertEqual(tb._last_added, 105)

    @kernels.with_kernel
    def test_token_bucket_raise_when_empty(self):
        self.monotonic_mock.return_value = 99
        tb = policies.TokenBucket(1, 1, True)
        with self.assertRaises(policies.Unavailable):
            kernels.run(tb)
        self.assertEqual(tb._num_tokens, 0)

    def test_invalid_args(self):
        with self.assertRaises(AssertionError):
            policies.TokenBucket(0, 1, False)
        with self.assertRaises(AssertionError):
            policies.TokenBucket(-1, 1, False)
        with self.assertRaises(AssertionError):
            policies.TokenBucket(1, 0, False)
        with self.assertRaises(AssertionError):
            policies.TokenBucket(1, -1, False)

    def test_add_tokens(self):
        self.monotonic_mock.return_value = 99

        tb = policies.TokenBucket(0.5, 2, False)
        self.assertAlmostEqual(tb._token_rate, 0.5)
        self.assertAlmostEqual(tb._token_period, 2.0)
        self.assertEqual(tb._bucket_size, 2)
        self.assertEqual(tb._num_tokens, 0)
        self.assertEqual(tb._last_added, 99)

        tb._add_tokens()
        self.assertAlmostEqual(tb._num_tokens, 0)
        self.assertEqual(tb._last_added, 99)

        self.monotonic_mock.return_value = 100
        tb._add_tokens()
        self.assertAlmostEqual(tb._num_tokens, 0.5)
        self.assertEqual(tb._last_added, 100)

        tb._add_tokens()
        self.assertAlmostEqual(tb._num_tokens, 0.5)
        self.assertEqual(tb._last_added, 100)

        self.monotonic_mock.return_value = 101
        tb._add_tokens()
        self.assertAlmostEqual(tb._num_tokens, 1)
        self.assertEqual(tb._last_added, 101)

        tb._add_tokens()
        self.assertAlmostEqual(tb._num_tokens, 1)
        self.assertEqual(tb._last_added, 101)

        self.monotonic_mock.return_value = 109
        tb._add_tokens()
        self.assertAlmostEqual(tb._num_tokens, 2)
        self.assertEqual(tb._last_added, 109)


class RetryTest(unittest.TestCase):

    def test_no_retry(self):
        self.assertIsNone(policies.no_retry(0))
        self.assertIsNone(policies.no_retry(1))
        self.assertIsNone(policies.no_retry(2))

    def test_backoff(self):

        with self.assertRaises(AssertionError):
            policies.ExponentialBackoff(0, 1)
        with self.assertRaises(AssertionError):
            policies.ExponentialBackoff(-1, 1)
        with self.assertRaises(AssertionError):
            policies.ExponentialBackoff(1, 0)
        with self.assertRaises(AssertionError):
            policies.ExponentialBackoff(1, -1)

        backoff = policies.ExponentialBackoff(1, 13)
        self.assertEqual(backoff(0), 13 * 1)
        self.assertIsNone(backoff(1))
        self.assertIsNone(backoff(2))
        self.assertIsNone(backoff(3))

        backoff = policies.ExponentialBackoff(2, 13)
        self.assertEqual(backoff(0), 13 * 1)
        self.assertEqual(backoff(1), 13 * 2)
        self.assertIsNone(backoff(2))
        self.assertIsNone(backoff(3))

        backoff = policies.ExponentialBackoff(3, 13)
        self.assertEqual(backoff(0), 13 * 1)
        self.assertEqual(backoff(1), 13 * 2)
        self.assertEqual(backoff(2), 13 * 4)
        self.assertIsNone(backoff(3))


async def mocked_sleep(_):
    pass


if __name__ == '__main__':
    unittest.main()
