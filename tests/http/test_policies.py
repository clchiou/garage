import unittest

from garage.http import policies


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
