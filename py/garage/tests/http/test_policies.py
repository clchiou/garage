import unittest

from garage.http import policies


class TokenBucketTest(unittest.TestCase):

    def test_add_tokens(self):
        now = [0]
        tb = policies.TokenBucket(0.5, 2, clock=lambda: now[0])

        self.assertAlmostEqual(tb._num_tokens, 0)

        tb._add_tokens()
        self.assertAlmostEqual(tb._num_tokens, 0)

        now[0] = 1
        tb._add_tokens()
        self.assertAlmostEqual(tb._num_tokens, 0.5)

        tb._add_tokens()
        self.assertAlmostEqual(tb._num_tokens, 0.5)

        now[0] = 2
        tb._add_tokens()
        self.assertAlmostEqual(tb._num_tokens, 1)

        tb._add_tokens()
        self.assertAlmostEqual(tb._num_tokens, 1)

        now[0] = 10
        tb._add_tokens()
        self.assertAlmostEqual(tb._num_tokens, 2)


class RetryPolicyTest(unittest.TestCase):

    def test_no_retry(self):
        no_retry = policies.NoRetry()()
        with self.assertRaises(StopIteration):
            next(no_retry)

    def test_binary_exponential_backoff(self):
        N = 16
        backoffs = list(policies.BinaryExponentialBackoff(N)())
        self.assertEqual(N, len(backoffs))
        for i, backoff in zip(range(N), backoffs):
            self.assertLessEqual(0, backoff)
            self.assertLessEqual(backoff, 2 ** (i + 1) - 1)


if __name__ == '__main__':
    unittest.main()
