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
import requests.cookies

try:
    import lxml.etree
    from lxml.etree import fromstring
except ImportError:
    fromstring = None

from garage.assertions import ASSERT
from garage.http import policies


LOG = logging.getLogger(__name__)


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


def _patch_session(session):
    """Patch requests.Session.send for better logging."""
    def _send(request, **kwargs):
        if LOG.isEnabledFor(logging.DEBUG):
            for name, value in request.headers.items():
                LOG.debug('<<< %s: %s', name, value)
            LOG.debug('send_kwargs %r', kwargs)
        response = send(request, **kwargs)
        if LOG.isEnabledFor(logging.DEBUG):
            for name, value in response.headers.items():
                LOG.debug('>>> %s: %s', name, value)
        return response
    send = session.send
    session.send = _send


class Client(_ClientMixin):

    #
    # NOTE:
    #   Session.{get,...} does a _LOT_ of extra work than just bare
    #   Session.send.  Your life would be much easier if you stay above
    #   Session.{get,...} instead of Session.send.
    #

    def __init__(self, *,
                 rate_limit=None,
                 retry_policy=None,
                 _session=None,
                 _sleep=time.sleep):
        self._session = _session or requests.Session()
        self._rate_limit = rate_limit or policies.Unlimited()
        self._retry_policy = retry_policy or policies.NoRetry()
        self._sleep = _sleep
        _patch_session(self._session)

    @property
    def headers(self):
        return self._session.headers

    @property
    def cookies(self):
        return self._session.cookies

    def update_cookies(self, cookie_dict):
        """Update cookies with a dict-like object."""
        requests.cookies.cookiejar_from_dict(
            cookie_dict, self._session.cookies
        )

    def send(self, request, **kwargs):
        LOG.debug('%s %s', request.method, request.uri)
        _check_kwargs(kwargs, _SEND_ARG_NAMES)
        method = getattr(self._session, request.method.lower())
        kwargs.update(request.kwargs)
        retry = self._retry_policy()
        retry_count = 0
        while True:
            try:
                return self._send(method, request, kwargs, retry_count)
            except Exception:
                backoff = next(retry, None)
                if backoff is None:
                    raise
            self._sleep(backoff)
            retry_count += 1

    def _send(self, method, request, kwargs, retry_count):
        try:
            with self._rate_limit:
                if retry_count:
                    LOG.warning(
                        'retry %d times: %s %s',
                        retry_count, request.method, request.uri,
                    )
                response = method(request.uri, **kwargs)
                response.raise_for_status()
                return Response(response)
        except requests.RequestException as exc:
            if exc.response is not None:
                status_code = exc.response.status_code
            else:
                status_code = '???'
            LOG.warning(
                'encounter HTTP error: status=%s, %s %s',
                status_code, request.method, request.uri, exc_info=True,
            )
            raise HttpError('%s %s' % (request.method, request.uri)) from exc
        except Exception:
            LOG.warning(
                'encounter generic error: %s %s',
                request.method, request.uri, exc_info=True,
            )
            raise


class ForwardingClient(_ClientMixin):
    """A client that forwards requests to the underlying client."""

    def __init__(self, client):
        self.client = client

    @property
    def headers(self):
        return self.client.headers

    def update_cookies(self, cookie_dict):
        self.client.update_cookies(cookie_dict)

    def send(self, request, **kwargs):
        request = self.on_request(request)
        response = self.client.send(request, **kwargs)
        return self.on_response(request, response)

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

    def __str__(self):
        return ('Request(%r, %r, **%r)' %
                (self.method, self.uri, self.kwargs))

    __repr__ = __str__

    @property
    def headers(self):
        return self.kwargs.setdefault('headers', {})


class Response:
    """A thin wrapper of requests.Response."""

    def __init__(self, response):
        self._response = response

    def __getattr__(self, name):
        return getattr(self._response, name)

    def dom(self, encoding=None, errors=None):

        if fromstring is None:
            raise RuntimeError('lxml.etree is not installed')

        #
        # The caller intends to handle character encoding error in a way
        # that is different from lxml's (lxml refuses to parse the rest
        # of the document if there is any encoding error in the middle,
        # but neither does it report the error).
        #
        # lxml's strict-but-silent policy is counterproductive because
        # Web is full of malformed documents, and it should either be
        # lenient about the error, or raise it to the caller, not a mix
        # of both as it is right now.
        #
        if encoding and errors:
            html = self.content.decode(encoding=encoding, errors=errors)
            parser = _get_parser(None)
            return fromstring(html, parser)

        ASSERT.none(errors)

        parser = _get_parser(encoding or self.encoding)
        return fromstring(self.content, parser)


@functools.lru_cache(maxsize=8)
def _get_parser(encoding):
    return lxml.etree.HTMLParser(encoding=encoding)
