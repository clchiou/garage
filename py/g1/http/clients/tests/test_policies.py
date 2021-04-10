import unittest
import unittest.mock

from g1.asyncs import kernels
from g1.asyncs.bases import tasks
from g1.http.clients import policies


class EventLogTest(unittest.TestCase):

    def assert_event_log(self, log, expect):
        self.assertEqual(list(log._log), expect)

    def test_event_log(self):
        log = policies._EventLog(1)
        self.assert_event_log(log, [])
        self.assertEqual(log.count(), 0)
        self.assertEqual(log.count(1), 0)

        log.add(1)
        self.assert_event_log(log, [1])

        with self.assertRaisesRegex(AssertionError, 'expect x > 1, not 1'):
            log.add(1)

        log.add(2)
        self.assert_event_log(log, [2])

        self.assertEqual(log.count(), 1)
        self.assertEqual(log.count(2), 1)
        self.assertEqual(log.count(3), 0)

        log.clear()
        self.assert_event_log(log, [])

    def test_count(self):
        log = policies._EventLog(3)
        log.add(1)
        log.add(3)
        log.add(5)
        self.assert_event_log(log, [1, 3, 5])
        self.assertEqual(log.count(), 3)
        self.assertEqual(log.count(0), 3)
        self.assertEqual(log.count(1), 3)
        self.assertEqual(log.count(2), 2)
        self.assertEqual(log.count(3), 2)
        self.assertEqual(log.count(4), 1)
        self.assertEqual(log.count(5), 1)
        self.assertEqual(log.count(6), 0)


class TristateBreakerTest(unittest.TestCase):

    def assert_breaker(self, breaker, state, log, num_concurrent_requests):
        self.assertIs(breaker._state, state)
        self.assertEqual(list(breaker._event_log._log), log)
        self.assertEqual(
            breaker._num_concurrent_requests, num_concurrent_requests
        )

    @staticmethod
    def make(
        failure_threshold, failure_period, failure_timeout, success_threshold
    ):
        return policies.TristateBreaker(
            key='test',
            failure_threshold=failure_threshold,
            failure_period=failure_period,
            failure_timeout=failure_timeout,
            success_threshold=success_threshold,
        )

    @kernels.with_kernel
    def test_context_green(self):
        breaker = self.make(2, 1, 1, 2)
        self.assert_breaker(breaker, policies._States.GREEN, [], 0)

        self.assertIs(kernels.run(breaker.__aenter__()), breaker)
        self.assert_breaker(breaker, policies._States.GREEN, [], 1)

        self.assertIsNone(kernels.run(breaker.__aexit__(None, None, None)))
        self.assert_breaker(breaker, policies._States.GREEN, [], 0)

    @kernels.with_kernel
    def test_context_yellow_one_at_a_time(self):
        breaker = self.make(2, 1, 1, 2)
        breaker._change_state_yellow()
        self.assert_breaker(breaker, policies._States.YELLOW, [], 0)

        self.assertIs(kernels.run(breaker.__aenter__()), breaker)
        self.assert_breaker(breaker, policies._States.YELLOW, [], 1)

        aenter_task = tasks.spawn(breaker.__aenter__())
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        self.assertFalse(aenter_task.is_completed())

        aexit_task = tasks.spawn(breaker.__aexit__(None, None, None))
        kernels.run(timeout=0.01)

        self.assertTrue(aexit_task.is_completed())
        self.assertIsNone(aexit_task.get_result_nonblocking())

        self.assertTrue(aenter_task.is_completed())
        self.assertIs(aenter_task.get_result_nonblocking(), breaker)

        self.assert_breaker(breaker, policies._States.YELLOW, [], 1)

    @kernels.with_kernel
    def test_context_yellow_change_state_red(self):
        breaker = self.make(2, 1, 1, 2)
        breaker._change_state_yellow()
        self.assert_breaker(breaker, policies._States.YELLOW, [], 0)

        self.assertIs(kernels.run(breaker.__aenter__()), breaker)
        self.assert_breaker(breaker, policies._States.YELLOW, [], 1)

        aenter_task = tasks.spawn(breaker.__aenter__())
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        self.assertFalse(aenter_task.is_completed())

        breaker._change_state_red(99)
        kernels.run(breaker.__aexit__(None, None, None), timeout=0.01)

        self.assertTrue(aenter_task.is_completed())
        with self.assertRaisesRegex(
            policies.Unavailable, r'circuit breaker became disconnected: test'
        ):
            aenter_task.get_result_nonblocking()

        self.assert_breaker(breaker, policies._States.RED, [99], 0)

    @kernels.with_kernel
    @unittest.mock.patch.object(policies, 'time')
    def test_context_red(self, mock_time):
        mock_monotonic = mock_time.monotonic
        breaker = self.make(2, 1, 1, 2)

        mock_monotonic.side_effect = [100]
        breaker._change_state_red(99)
        self.assert_breaker(breaker, policies._States.RED, [99], 0)

        with self.assertRaisesRegex(
            policies.Unavailable, r'circuit breaker disconnected: test'
        ):
            kernels.run(breaker.__aenter__())
        self.assert_breaker(breaker, policies._States.RED, [99], 0)

    @kernels.with_kernel
    @unittest.mock.patch.object(policies, 'time')
    def test_context_red_timeout(self, mock_time):
        mock_monotonic = mock_time.monotonic
        breaker = self.make(2, 1, 1, 2)

        mock_monotonic.side_effect = [101]
        breaker._change_state_red(99)
        self.assert_breaker(breaker, policies._States.RED, [99], 0)

        self.assertIs(kernels.run(breaker.__aenter__()), breaker)
        self.assert_breaker(breaker, policies._States.YELLOW, [], 1)

    @unittest.mock.patch.object(policies, 'time')
    def test_notify_success(self, mock_time):
        mock_monotonic = mock_time.monotonic
        breaker = self.make(2, 1, 1, 2)

        breaker._event_log.add(1)
        self.assert_breaker(breaker, policies._States.GREEN, [1], 0)
        breaker.notify_success()
        self.assert_breaker(breaker, policies._States.GREEN, [], 0)

        mock_monotonic.side_effect = [99, 100]
        breaker._change_state_yellow()
        self.assert_breaker(breaker, policies._States.YELLOW, [], 0)
        breaker.notify_success()
        self.assert_breaker(breaker, policies._States.YELLOW, [99], 0)
        breaker.notify_success()
        self.assert_breaker(breaker, policies._States.GREEN, [], 0)

        breaker._change_state_red(2)
        self.assert_breaker(breaker, policies._States.RED, [2], 0)
        breaker.notify_success()
        self.assert_breaker(breaker, policies._States.RED, [2], 0)

    @unittest.mock.patch.object(policies, 'time')
    def test_notify_failure(self, mock_time):
        mock_monotonic = mock_time.monotonic
        breaker = self.make(2, 1, 1, 2)

        mock_monotonic.side_effect = [99, 100]
        self.assert_breaker(breaker, policies._States.GREEN, [], 0)
        breaker.notify_failure()
        self.assert_breaker(breaker, policies._States.GREEN, [99], 0)
        breaker.notify_failure()
        self.assert_breaker(breaker, policies._States.RED, [100], 0)

        mock_monotonic.side_effect = [101]
        breaker._change_state_yellow()
        self.assert_breaker(breaker, policies._States.YELLOW, [], 0)
        breaker.notify_failure()
        self.assert_breaker(breaker, policies._States.RED, [101], 0)

        breaker.notify_failure()
        self.assert_breaker(breaker, policies._States.RED, [101], 0)

    def test_change_state(self):
        breaker = self.make(1, 1, 1, 1)
        self.assert_breaker(breaker, policies._States.GREEN, [], 0)

        breaker._event_log.add(1)
        self.assert_breaker(breaker, policies._States.GREEN, [1], 0)

        breaker._change_state_yellow()
        self.assert_breaker(breaker, policies._States.YELLOW, [], 0)

        breaker._change_state_red(2)
        self.assert_breaker(breaker, policies._States.RED, [2], 0)

        breaker._change_state_green()
        self.assert_breaker(breaker, policies._States.GREEN, [], 0)


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
        with self.assertRaisesRegex(
            policies.Unavailable, r'rate limit exceeded'
        ):
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
