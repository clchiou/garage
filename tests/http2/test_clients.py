import unittest

import requests

from garage.http2 import clients


class TestClient(unittest.TestCase):

    def test_client(self):
        req_to_rep = {
            ('GET', 'uri_1'): 'hello world',
            ('GET', 'uri_2'): Exception('error_2'),
        }
        client = clients.Client(
            _session_cls=lambda: MockSession(req_to_rep),
            _sleep=fake_sleep,
        )

        rep = client.send(clients.Request('GET', 'uri_1'))
        self.assertEqual('hello world', rep._response)

        with self.assertRaisesRegex(Exception, 'error_2'):
            client.send(clients.Request('GET', 'uri_2'))


class MockSession:

    def __init__(self, req_to_rep):
        self._req_to_rep = req_to_rep

    def send(self, request):
        assert isinstance(request, requests.Request)
        response = self._req_to_rep[(request.method, request.url)]
        if isinstance(response, Exception):
            raise response
        return response


def fake_sleep(seconds):
    pass


if __name__ == '__main__':
    unittest.main()
