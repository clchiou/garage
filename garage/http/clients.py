"""A thin layer on top of the requests package that provides niceties
such as retry policy, rate limit, and more logging.
"""

__all__ = [
    'HttpError',
    'Client',
    'ForwardingClient',
    'Request',
    'Response',
]

import functools
import time
import logging

import requests

try:
    import lxml.etree
except ImportError:
    pass

from garage.http import policies


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


_REQUEST_ARG_NAMES = frozenset(
    'headers files data params auth cookies hooks json'.split()
)


_SEND_ARG_NAMES = frozenset(
    'verify proxies stream cert timeout allow_redirects'.split()
)


_ALL_ARG_NAMES = _REQUEST_ARG_NAMES | _SEND_ARG_NAMES


class HttpError(Exception):
    pass


def _check_kwargs(kwargs, arg_names):
    names = set(kwargs) - arg_names
    if names:
        raise TypeError('not expect these keyword arguments: %s' %
                        ', '.join(sorted(names)))


def _make_method(method):
    def http_method(self, uri, **kwargs):
        _check_kwargs(kwargs, _ALL_ARG_NAMES)
        req_kwargs = {
            key: arg for key, arg in kwargs.items()
            if key in _REQUEST_ARG_NAMES
        }
        send_kwargs = {
            key: arg for key, arg in kwargs.items()
            if key in _SEND_ARG_NAMES
        }
        return self.send(Request(method, uri, **req_kwargs), **send_kwargs)
    return http_method


class _ClientMixin:

    get = _make_method('GET')
    head = _make_method('HEAD')
    post = _make_method('POST')
    put = _make_method('PUT')


class Client(_ClientMixin):

    def __init__(self, *,
                 rate_limit=None,
                 retry_policy=None,
                 _session=None,
                 _sleep=time.sleep):
        self._session = _session or requests.Session()
        self._rate_limit = rate_limit or policies.Unlimited()
        self._retry_policy = retry_policy or policies.NoRetry()
        self._sleep = _sleep

    @property
    def headers(self):
        return self._session.headers

    def send(self, request, **kwargs):
        LOG.debug('%s %s', request.method, request.uri)
        _check_kwargs(kwargs, _SEND_ARG_NAMES)
        rreq = request._make_request()
        retry = self._retry_policy()
        retry_count = 0
        while True:
            try:
                return self._send(request, rreq, kwargs, retry_count)
            except BaseException:
                backoff = next(retry, None)
                if backoff is None:
                    raise
            self._sleep(backoff)
            retry_count += 1

    def _send(self, request, rreq, kwargs, retry_count):
        try:
            with self._rate_limit:
                if retry_count:
                    LOG.warning('Retry %d times of %s %s',
                                retry_count, request.method, request.uri)
                if LOG.isEnabledFor(logging.DEBUG):
                    for name, value in rreq.headers.items():
                        LOG.debug('<<< %s: %s', name, value)
                rrep = self._session.send(rreq.prepare(), **kwargs)
                if LOG.isEnabledFor(logging.DEBUG):
                    for name, value in rrep.headers.items():
                        LOG.debug('>>> %s: %s', name, value)
                rrep.raise_for_status()
                return Response(rrep)
        except requests.RequestException as exc:
            if exc.response is not None:
                status_code = exc.response.status_code
            else:
                status_code = '?'
            LOG.warning('HTTP error with status code %s when %s %s',
                        status_code, request.method, request.uri,
                        exc_info=True)
            raise HttpError('%s %s' % (request.method, request.uri)) from exc
        except BaseException:
            LOG.warning('Generic error when %s %s',
                        request.method, request.uri, exc_info=True)
            raise


class ForwardingClient(_ClientMixin):
    """A client that forwards requests to the underlying client."""

    def __init__(self, client):
        self.client = client

    @property
    def headers(self):
        return self.client.headers

    def send(self, request, **kwargs):
        request = self.on_request(request)
        response = self.client.send(request, **kwargs)
        response = self.on_response(request, response)
        return response

    def on_request(self, request):
        """Hook for modifying request."""
        return request

    def on_response(self, _, response):
        """Hook for modifying response."""
        return response


class Request:
    """A thin wrapper of requests.Request."""

    def __init__(self, method, uri, **kwargs):
        _check_kwargs(kwargs, _REQUEST_ARG_NAMES)
        self.method = method
        self.uri = uri
        self.kwargs = kwargs

    def _make_request(self):
        return requests.Request(self.method, self.uri, **self.kwargs)


class Response:
    """A thin wrapper of requests.Response."""

    def __init__(self, response):
        object.__setattr__(self, '_response', response)

    def __getattr__(self, name):
        return getattr(self._response, name)

    def dom(self, encoding=None):
        try:
            fromstring = lxml.etree.fromstring
        except NameError as exc:
            raise RuntimeError('lxml.etree is not installed') from exc
        parser = _get_parser(encoding or self.encoding)
        return fromstring(self.content, parser)


@functools.lru_cache(maxsize=8)
def _get_parser(encoding):
    return lxml.etree.HTMLParser(encoding=encoding)
