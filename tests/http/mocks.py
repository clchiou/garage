__all__ = [
    'MockSession',
    'MockResponse',
    'fake_sleep',
]

import requests


class MockSession:
    """Mock of requests.Session."""

    def __init__(self, req_to_rep):
        self._req_to_rep = req_to_rep
        self._logs = []

    def head(self, url, **kwargs):
        return self.send(requests.Request('HEAD', url, **kwargs).prepare())

    def get(self, url, **kwargs):
        return self.send(requests.Request('GET', url, **kwargs).prepare())

    def post(self, url, **kwargs):
        return self.send(requests.Request('POST', url, **kwargs).prepare())

    def put(self, url, **kwargs):
        return self.send(requests.Request('PUT', url, **kwargs).prepare())

    def send(self, request):
        assert isinstance(request, requests.PreparedRequest)
        self._logs.append(request)
        rep = self._req_to_rep[(request.method, request.url)]
        if isinstance(rep, Exception):
            raise rep
        elif isinstance(rep, list):
            return MockResponse(*rep.pop(0))
        else:
            return MockResponse(*rep)


class MockResponse:
    """Mock of requests.Response."""

    encoding = 'ascii'

    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            raise requests.HTTPError('http error', response=self)


def fake_sleep(_):
    """Use this in place of time.sleep in tests."""
    pass
