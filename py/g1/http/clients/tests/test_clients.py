import unittest
import unittest.mock

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
                requests.RequestException
        self.mock_session.get.return_value = self.mock_response


class SessionTest(TestCaseBase):

    @classmethod
    def setUpClass(cls):
        cls.executor = executors.Executor(max_executors=1)

    @kernels.with_kernel
    def test_success(self):
        session = clients.Session(executor=self.executor)
        self.set_mock_response(200)
        self.assertIs(
            kernels.run(session.send(self.REQUEST)),
            self.mock_response,
        )
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
        self.set_mock_response(404)
        with self.assertRaises(requests.RequestException):
            kernels.run(session.send(self.REQUEST))
        self.mock_session.get.assert_has_calls([
            unittest.mock.call(self.URL),
            unittest.mock.call().raise_for_status(),
            unittest.mock.call(self.URL),
            unittest.mock.call().raise_for_status(),
            unittest.mock.call(self.URL),
            unittest.mock.call().raise_for_status(),
        ])

    @kernels.with_kernel
    def test_cache_key(self):
        session = clients.Session(executor=self.executor)
        self.set_mock_response(200)
        for _ in range(3):
            self.assertIs(
                kernels.run(session.send(self.REQUEST, cache_key='x')),
                self.mock_response,
            )
        self.mock_session.get.assert_called_once_with(self.URL)

    @kernels.with_kernel
    def test_sticky_key(self):
        session = clients.Session(executor=self.executor)
        self.set_mock_response(200)
        for _ in range(3):
            self.assertIs(
                kernels.run(session.send(self.REQUEST, sticky_key='y')),
                self.mock_response,
            )
        self.mock_session.get.assert_called_once_with(self.URL)

    @kernels.with_kernel
    def test_cache_key_and_sticky_key(self):
        session = clients.Session(executor=self.executor)
        with self.assertRaisesRegex(AssertionError, r'expect at most one:'):
            kernels.run(
                session.send(self.REQUEST, cache_key='x', sticky_key='y')
            )


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
        self.assertIs(
            kernels.run(session.send(self.REQUEST, priority=1)),
            self.mock_response,
        )
        self.mock_session.get.assert_called_once_with(self.URL)


if __name__ == '__main__':
    unittest.main()
