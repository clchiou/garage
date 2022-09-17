import unittest
import unittest.mock

import contextlib
import http.server
import tempfile
import threading
from pathlib import Path

import requests

from g1.asyncs import kernels
from g1.http.clients import bases
from g1.http.clients import clients
from g1.http.clients import policies
from g1.threads import executors


class TestCaseBase(unittest.TestCase):

    URL = 'http://localhost/index.html'
    REQUEST = bases.Request('GET', URL)

    executor = None

    @classmethod
    def tearDownClass(cls):
        cls.executor.shutdown()
        cls.executor.join()

    def setUp(self):
        super().setUp()
        mock_session_class = unittest.mock.patch(
            bases.__name__ + '.requests.Session'
        ).start()
        self.mock_session = mock_session_class.return_value
        self.mock_response = None

    def tearDown(self):
        unittest.mock.patch.stopall()
        super().tearDown()

    def set_mock_response(self, status_code):
        self.mock_response = unittest.mock.Mock(
            spec_set=dir(requests.Response())
        )
        self.mock_response.status_code = status_code
        if 400 <= status_code < 600:
            self.mock_response.raise_for_status.side_effect = \
                requests.RequestException(response=self.mock_response)
        self.mock_response.history = []
        self.mock_session.get.return_value = self.mock_response


class SessionTest(TestCaseBase):

    @classmethod
    def setUpClass(cls):
        cls.executor = executors.Executor(max_executors=1)

    def assert_breaker(self, breaker, state, log, num_concurrent_requests):
        self.assertIs(breaker._state, state)
        self.assertEqual(list(breaker._event_log._log), log)
        self.assertEqual(
            breaker._num_concurrent_requests, num_concurrent_requests
        )

    @kernels.with_kernel
    def test_success(self):
        session = clients.Session(executor=self.executor)
        self.set_mock_response(200)
        response = kernels.run(session.send(self.REQUEST))
        self.assertIsNot(response, self.mock_response)
        self.assertIsInstance(response, bases.Response)
        self.mock_session.get.assert_called_once_with(self.URL)

    @kernels.with_kernel
    def test_error(self):
        session = clients.Session(
            executor=self.executor,
            retry=policies.ExponentialBackoff(2, 0.001),
        )
        self.mock_session.get.side_effect = Exception('some error')
        with self.assertRaisesRegex(Exception, r'some error'):
            kernels.run(session.send(self.REQUEST))
        self.mock_session.get.assert_called_once_with(self.URL)

    @kernels.with_kernel
    @unittest.mock.patch.object(policies, 'time')
    def test_circuit_breaker(self, mock_time):
        mock_monotonic = mock_time.monotonic
        mock_monotonic.side_effect = [
            99, 100, 101, 102, 103, 104, 105, 106, 107
        ]
        self.mock_session.get.side_effect = Exception('some error')
        circuit_breakers = policies.TristateBreakers(
            failure_threshold=2,
            failure_period=1,
            failure_timeout=1,
            success_threshold=2,
        )
        breaker = circuit_breakers.get('localhost')
        session = clients.Session(
            executor=self.executor,
            circuit_breakers=circuit_breakers,
        )

        self.assert_breaker(breaker, policies._States.GREEN, [], 0)

        with self.assertRaisesRegex(Exception, r'some error'):
            kernels.run(session.send(self.REQUEST))
        self.assert_breaker(breaker, policies._States.GREEN, [99], 0)

        with self.assertRaisesRegex(Exception, r'some error'):
            kernels.run(session.send(self.REQUEST))
        self.assert_breaker(breaker, policies._States.RED, [100], 0)

        with self.assertRaisesRegex(
            policies.Unavailable, r'circuit breaker disconnected'
        ):
            kernels.run(session.send(self.REQUEST))
        self.assert_breaker(breaker, policies._States.RED, [100], 0)

        with self.assertRaisesRegex(Exception, r'some error'):
            kernels.run(session.send(self.REQUEST))
        self.assert_breaker(breaker, policies._States.RED, [103], 0)

        self.mock_session.get.side_effect = None
        self.set_mock_response(404)

        with self.assertRaisesRegex(
            policies.Unavailable, r'circuit breaker disconnected'
        ):
            kernels.run(session.send(self.REQUEST))
        self.assert_breaker(breaker, policies._States.RED, [103], 0)

        with self.assertRaises(requests.RequestException):
            kernels.run(session.send(self.REQUEST))
        self.assert_breaker(breaker, policies._States.YELLOW, [106], 0)

        self.set_mock_response(200)

        kernels.run(session.send(self.REQUEST))
        self.assert_breaker(breaker, policies._States.GREEN, [], 0)

    @kernels.with_kernel
    def test_http_error_no_retry(self):
        session = clients.Session(executor=self.executor)
        self.set_mock_response(404)
        with self.assertRaises(requests.RequestException):
            kernels.run(session.send(self.REQUEST))
        self.mock_session.get.assert_called_once_with(self.URL)

    @kernels.with_kernel
    def test_http_error_retry(self):
        session = clients.Session(
            executor=self.executor,
            retry=policies.ExponentialBackoff(2, 0.001),
        )
        self.set_mock_response(500)
        with self.assertRaises(requests.RequestException):
            kernels.run(session.send(self.REQUEST))
        self.mock_session.get.assert_has_calls([
            unittest.mock.call(self.URL),
            unittest.mock.call().close(),
            unittest.mock.call(self.URL),
            unittest.mock.call().close(),
            unittest.mock.call(self.URL),
            unittest.mock.call().close(),
        ])

    @kernels.with_kernel
    def test_http_error_no_retry_4xx(self):
        session = clients.Session(
            executor=self.executor,
            retry=policies.ExponentialBackoff(2, 0.001),
        )
        self.set_mock_response(404)
        with self.assertRaises(requests.RequestException):
            kernels.run(session.send(self.REQUEST))
        self.mock_session.get.assert_called_once_with(self.URL)

    def _assert_cache_stats(
        self, cache_stats, num_hits, num_misses, num_revalidations
    ):
        self.assertEqual(
            cache_stats,
            bases.Sender.CacheStats(
                num_hits=num_hits,
                num_misses=num_misses,
                num_revalidations=num_revalidations,
            ),
        )

    def assert_cache_stats(self, session, *args):
        self._assert_cache_stats(session._sender._cache_stats, *args)

    def assert_sticky_cache_stats(self, session, *args):
        self._assert_cache_stats(session._sender._unbounded_cache_stats, *args)

    @kernels.with_kernel
    def test_cache_key(self):
        session = clients.Session(executor=self.executor)
        self.assert_cache_stats(session, 0, 0, 0)
        self.assert_sticky_cache_stats(session, 0, 0, 0)
        self.set_mock_response(200)
        response = kernels.run(session.send(self.REQUEST, cache_key='x'))
        self.assert_cache_stats(session, 0, 1, 0)
        self.assert_sticky_cache_stats(session, 0, 0, 0)
        for i in range(3):
            self.assertIs(
                kernels.run(session.send(self.REQUEST, cache_key='x')),
                response,
            )
            self.assert_cache_stats(session, i + 1, 1, 0)
            self.assert_sticky_cache_stats(session, 0, 0, 0)
        self.mock_session.get.assert_called_once_with(self.URL)

    @kernels.with_kernel
    def test_sticky_key(self):
        session = clients.Session(executor=self.executor)
        self.assert_cache_stats(session, 0, 0, 0)
        self.assert_sticky_cache_stats(session, 0, 0, 0)
        self.set_mock_response(200)
        response = kernels.run(session.send(self.REQUEST, sticky_key='y'))
        self.assert_cache_stats(session, 0, 0, 0)
        self.assert_sticky_cache_stats(session, 0, 1, 0)
        for i in range(3):
            self.assertIs(
                kernels.run(session.send(self.REQUEST, sticky_key='y')),
                response,
            )
            self.assert_cache_stats(session, 0, 0, 0)
            self.assert_sticky_cache_stats(session, i + 1, 1, 0)
        self.mock_session.get.assert_called_once_with(self.URL)

    @kernels.with_kernel
    def test_cache_key_and_sticky_key(self):
        session = clients.Session(executor=self.executor)
        with self.assertRaisesRegex(AssertionError, r'expect at most one:'):
            kernels.run(
                session.send(self.REQUEST, cache_key='x', sticky_key='y')
            )

    @kernels.with_kernel
    def test_cache_revalidate(self):
        session = clients.Session(executor=self.executor)
        self.assert_cache_stats(session, 0, 0, 0)
        self.assert_sticky_cache_stats(session, 0, 0, 0)
        self.set_mock_response(200)
        for i in range(3):
            kernels.run(
                session.send(
                    self.REQUEST, cache_key='x', cache_revalidate=True
                )
            )
            self.assert_cache_stats(session, 0, 1, i)
            self.assert_sticky_cache_stats(session, 0, 0, 0)
        self.mock_session.get.assert_has_calls([
            unittest.mock.call(self.URL),
            unittest.mock.call().close(),
            unittest.mock.call(self.URL),
            unittest.mock.call().close(),
            unittest.mock.call(self.URL),
            unittest.mock.call().close(),
        ])


class PrioritySessionTest(TestCaseBase):

    @classmethod
    def setUpClass(cls):
        cls.executor = executors.PriorityExecutor(
            max_executors=1, default_priority=0
        )

    @kernels.with_kernel
    def test_success(self):
        # TODO: How to test that requests are executed in order?
        session = clients.Session(executor=self.executor)
        self.set_mock_response(200)
        response = kernels.run(session.send(self.REQUEST, priority=1))
        self.assertIsNot(response, self.mock_response)
        self.assertIsInstance(response, bases.Response)
        self.mock_session.get.assert_called_once_with(self.URL)


class ResponseTest(unittest.TestCase):

    def test_history_copy(self):
        mock_response = unittest.mock.Mock()
        mock_response.history = [mock_response]
        response = bases.Response(mock_response, None)
        self.assertEqual(len(response.history), 1)
        self.assertIsInstance(response.history[0], bases.Response)
        self.assertIsNone(response.history[0].history)


class RecvfileTest(unittest.TestCase):

    class TestHandler(http.server.SimpleHTTPRequestHandler):

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs, directory=Path(__file__).parent)

        def log_message(self, *_):
            pass  # Suppress logging in test.

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cls_exit_stack = contextlib.ExitStack()

        cls.server = cls.cls_exit_stack.enter_context(
            http.server.ThreadingHTTPServer(('127.0.0.1', 0), cls.TestHandler)
        )

        cls.server_thread = threading.Thread(target=cls.server.serve_forever)
        cls.cls_exit_stack.callback(cls.server_thread.join)
        cls.server_thread.start()

        cls.cls_exit_stack.callback(cls.server.shutdown)

        cls.server_port = cls.server.socket.getsockname()[1]

    @classmethod
    def tearDownClass(cls):
        cls.cls_exit_stack.close()
        super().tearDownClass()

    @kernels.with_kernel
    def test_recvfile(self):
        test_path = Path(__file__)
        session = clients.Session()
        request = bases.Request(
            'GET',
            'http://127.0.0.1:%d/%s' % (self.server_port, test_path.name),
        )

        with tempfile.TemporaryFile() as output:
            with kernels.run(session.send(request, stream=True)) as response:
                kernels.run(response.recvfile(output))
            output.seek(0)
            self.assertEqual(output.read(), test_path.read_bytes())

        # Check that response is closed.
        self.assertTrue(response.raw._fp.isclosed())
        self.assertIsNone(response.raw._fp.fp)


if __name__ == '__main__':
    unittest.main()
