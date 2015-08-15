import unittest

import requests

from garage.http import clients
from garage.http import policies

from tests.http.mocks import *


class ClientTest(unittest.TestCase):

    def test_client(self):
        req_to_rep = {
            ('GET', 'http://uri_1/'): (200, 'hello world'),
            ('GET', 'http://uri_2/'): Exception('error_2'),
            ('GET', 'http://uri_3/'): (200, 'GET uri_3'),
            ('HEAD', 'http://uri_3/'): (200, 'HEAD uri_3'),
            ('POST', 'http://uri_3/'): (200, 'POST uri_3'),
            ('PUT', 'http://uri_3/'): (200, 'PUT uri_3'),
            ('GET', 'http://uri_4/'): (404, ''),
        }
        client = clients.Client(
            _session=MockSession(req_to_rep),
            _sleep=fake_sleep,
        )

        rep = client.send(clients.Request('GET', 'http://uri_1'))
        self.assertEqual('hello world', rep.content)

        with self.assertRaisesRegex(Exception, 'error_2'):
            client.send(clients.Request('GET', 'http://uri_2'))

        self.assertEqual('GET uri_3', client.get('http://uri_3').content)
        self.assertEqual('HEAD uri_3', client.head('http://uri_3').content)
        self.assertEqual('POST uri_3', client.post('http://uri_3').content)
        self.assertEqual('PUT uri_3', client.put('http://uri_3').content)

        with self.assertRaises(clients.HttpError):
            client.get('http://uri_4')

    def test_rate_limit(self):
        session = MockSession({
            ('GET', 'http://uri_1/'): [(200, 'tick'), (200, 'tock')],
        })
        client = clients.Client(
            rate_limit=TimedBomb(2),
            _session=session,
            _sleep=fake_sleep,
        )
        self.assertEqual('tick', client.get('http://uri_1').content)
        self.assertEqual('tock', client.get('http://uri_1').content)
        with self.assertRaisesRegex(Exception, 'Boom!'):
            client.get('http://uri_1')

    def test_no_retry(self):
        session = MockSession({('GET', 'http://uri_1/'): (400, 'error!')})
        client = clients.Client(
            retry_policy=policies.NoRetry(),
            _session=session,
            _sleep=fake_sleep,
        )
        with self.assertRaises(clients.HttpError):
            client.get('http://uri_1')
        self.assertEqual(1, len(session._logs))
        for req in session._logs:
            self.assertTrue(isinstance(req, requests.PreparedRequest))
            self.assertEqual('GET', req.method)
            self.assertEqual('http://uri_1/', req.url)

    def test_retry(self):
        N = 16
        session = MockSession({
            ('GET', 'http://uri_1/'): (400, 'error!'),
            ('GET', 'http://uri_2/'): [
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
        with self.assertRaises(clients.HttpError):
            client.get('http://uri_1')
        self.assertEqual(1 + N, len(session._logs))
        for req in session._logs:
            self.assertTrue(isinstance(req, requests.PreparedRequest))
            self.assertEqual('GET', req.method)
            self.assertEqual('http://uri_1/', req.url)

        session._logs.clear()
        self.assertEqual('success', client.get('http://uri_2').content)
        self.assertEqual(4, len(session._logs))
        for req in session._logs:
            self.assertTrue(isinstance(req, requests.PreparedRequest))
            self.assertEqual('GET', req.method)
            self.assertEqual('http://uri_2/', req.url)


class TimedBomb:

    def __init__(self, count):
        self.count = count

    def __enter__(self):
        self.count -= 1
        if self.count < 0:
            raise Exception('Boom!')

    def __exit__(self, *_):
        pass


if __name__ == '__main__':
    unittest.main()
