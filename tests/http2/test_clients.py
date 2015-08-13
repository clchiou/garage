import unittest

import requests

from garage.http2 import clients
from garage.http2 import policies


class TestClient(unittest.TestCase):

    def test_client(self):
        req_to_rep = {
            ('GET', 'uri_1'): (200, 'hello world'),
            ('GET', 'uri_2'): Exception('error_2'),
            ('GET', 'uri_3'): (200, 'GET uri_3'),
            ('HEAD', 'uri_3'): (200, 'HEAD uri_3'),
            ('POST', 'uri_3'): (200, 'POST uri_3'),
            ('PUT', 'uri_3'): (200, 'PUT uri_3'),
            ('GET', 'uri_4'): (404, ''),
        }
        client = clients.Client(
            _session=MockSession(req_to_rep),
            _sleep=fake_sleep,
        )

        rep = client.send(clients.Request('GET', 'uri_1'))
        self.assertEqual('hello world', rep.content)

        with self.assertRaisesRegex(Exception, 'error_2'):
            client.send(clients.Request('GET', 'uri_2'))

        self.assertEqual('GET uri_3', client.get('uri_3').content)
        self.assertEqual('HEAD uri_3', client.head('uri_3').content)
        self.assertEqual('POST uri_3', client.post('uri_3').content)
        self.assertEqual('PUT uri_3', client.put('uri_3').content)

        with self.assertRaisesRegex(requests.HTTPError, 'http error'):
            client.get('uri_4')

    def test_rate_limit(self):
        session = MockSession({
            ('GET', 'uri_1'): [(200, 'tick'), (200, 'tock')],
        })
        client = clients.Client(
            rate_limit=TimedBomb(2),
            _session=session,
            _sleep=fake_sleep,
        )
        self.assertEqual('tick', client.get('uri_1').content)
        self.assertEqual('tock', client.get('uri_1').content)
        with self.assertRaisesRegex(Exception, 'Boom!'):
            client.get('uri_1')

    def test_no_retry(self):
        session = MockSession({('GET', 'uri_1'): (400, 'error!')})
        client = clients.Client(
            retry_policy=policies.NoRetry(),
            _session=session,
            _sleep=fake_sleep,
        )
        with self.assertRaisesRegex(requests.HTTPError, 'http error'):
            client.get('uri_1')
        self.assertEqual(1, len(session._logs))
        for req in session._logs:
            self.assertTrue(isinstance(req, requests.Request))
            self.assertEqual('GET', req.method)
            self.assertEqual('uri_1', req.url)

    def test_retry(self):
        N = 16
        session = MockSession({
            ('GET', 'uri_1'): (400, 'error!'),
            ('GET', 'uri_2'): [
                (400, 'error!'),
                (400, 'error!'),
                (400, 'error!'),
                (200, 'success'),
            ],
        })
        client = clients.Client(
            retry_policy=policies.BinaryExponentialBackoff(N),
            _session=session,
            _sleep=fake_sleep,
        )

        session._logs.clear()
        with self.assertRaisesRegex(requests.HTTPError, 'http error'):
            client.get('uri_1')
        self.assertEqual(1 + N, len(session._logs))
        for req in session._logs:
            self.assertTrue(isinstance(req, requests.Request))
            self.assertEqual('GET', req.method)
            self.assertEqual('uri_1', req.url)

        session._logs.clear()
        self.assertEqual('success', client.get('uri_2').content)
        self.assertEqual(4, len(session._logs))
        for req in session._logs:
            self.assertTrue(isinstance(req, requests.Request))
            self.assertEqual('GET', req.method)
            self.assertEqual('uri_2', req.url)


class TimedBomb:

    def __init__(self, count):
        self.count = count

    def __enter__(self):
        self.count -= 1
        if self.count < 0:
            raise Exception('Boom!')

    def __exit__(self, *_):
        pass


class MockSession:

    def __init__(self, req_to_rep):
        self._req_to_rep = req_to_rep
        self._logs = []

    def send(self, request):
        assert isinstance(request, requests.Request)
        self._logs.append(request)
        rep = self._req_to_rep[(request.method, request.url)]
        if isinstance(rep, Exception):
            raise rep
        elif isinstance(rep, list):
            return MockResponse(*rep.pop(0))
        else:
            return MockResponse(*rep)


class MockResponse:

    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            raise requests.HTTPError('http error', response=self)


def fake_sleep(seconds):
    pass


if __name__ == '__main__':
    unittest.main()
