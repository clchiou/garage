import unittest

import requests

from garage.http2 import clients


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
            _session_cls=lambda: MockSession(req_to_rep),
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


class MockSession:

    def __init__(self, req_to_rep):
        self._req_to_rep = req_to_rep

    def send(self, request):
        assert isinstance(request, requests.Request)
        rep = self._req_to_rep[(request.method, request.url)]
        if isinstance(rep, Exception):
            raise rep
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
