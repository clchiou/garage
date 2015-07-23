"""HTTP client library."""

__all__ = [
    'HttpClient',
    'form',
]

import functools
import logging
import threading
import time

import lxml.etree
import requests

from startup import startup

from garage.app import ARGS
from garage.app import PARSE
from garage.app import PARSER
from garage.collections import make_fixed_attrs
from garage.http.error import HttpError
from garage.http.error import get_status_code


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/40.0.2214.111 Safari/537.36'
)


D = make_fixed_attrs(
    HTTP_MAX_REQUESTS=4,
    HTTP_RETRY=0,
    HTTP_RETRY_BASE_DELAY=1,
)


@startup
def add_arguments(parser: PARSER) -> PARSE:
    group = parser.add_argument_group(__name__)
    group.add_argument(
        '--http-max-requests', type=int, default=D.HTTP_MAX_REQUESTS,
        help='set max concurrent http requests (default %(default)s)')
    group.add_argument(
        '--http-retry', type=int, default=D.HTTP_RETRY,
        help='set number of retries on http error (default %(default)s)')
    group.add_argument(
        '--http-retry-base-delay', type=int, default=D.HTTP_RETRY_BASE_DELAY,
        help='set base delay between retries which grows exponentially '
             '(default %(default)s seconds)')


@startup
def configure_http_retry(args: ARGS):
    D.HTTP_MAX_REQUESTS = args.http_max_requests
    D.HTTP_RETRY = args.http_retry
    D.HTTP_RETRY_BASE_DELAY = args.http_retry_base_delay


def form(client, uri, encoding=None, **kwargs):
    """Post an HTML form interactively."""
    tree = client.get(uri, **kwargs).dom(encoding=encoding)
    xpath_expr = yield
    forms = tree.xpath(xpath_expr)
    if len(forms) != 1:
        raise HttpError('require one <form> but found %d' % len(forms))
    action_uri = forms[0].get('action')
    form_data = yield action_uri
    data = {}
    for form_input in forms[0].xpath('//input'):
        name = form_input.get('name')
        data[name] = form_data.get(name, form_input.get('value'))
    yield client.post(action_uri, data=data)


class HttpClient:
    """Wrapper of requests.Session object."""

    @staticmethod
    def make():
        return HttpClient(
            headers={'User-Agent': USER_AGENT},
            http_max_requests=D.HTTP_MAX_REQUESTS,
            http_retry=D.HTTP_RETRY,
            http_retry_base_delay=D.HTTP_RETRY_BASE_DELAY,
        )

    def __init__(self, *,
                 headers,
                 http_max_requests, http_retry, http_retry_base_delay):
        self.session = requests.Session()
        self.session.headers.update(headers)
        self.parsers = {}
        self.max_requests = threading.BoundedSemaphore(value=http_max_requests)
        self.http_retry = http_retry
        self.http_retry_base_delay = http_retry_base_delay
        # XXX: Monkey patching for logging.
        self._session_send = self.session.send
        self.session.send = self._send

    def get(self, uri, **kwargs):
        """Send a GET request."""
        LOG.debug('GET: uri=%s', uri)
        return self._request_with_retry(self.session.get, uri, kwargs)

    def post(self, uri, **kwargs):
        """Send a POST request."""
        LOG.debug('POST: uri=%s', uri)
        return self._request_with_retry(self.session.post, uri, kwargs)

    def head(self, uri, **kwargs):
        """Send a HEAD request."""
        LOG.debug('HEAD: uri=%s', uri)
        return self._request_with_retry(self.session.head, uri, kwargs)

    # NOTE: dom() is used in monkey patching only; don't call it!
    def dom(self, response, encoding=None):
        """Return a DOM object of the contents."""
        parser = self._get_parser(encoding or response.encoding)
        return lxml.etree.fromstring(response.content, parser)

    def _get_parser(self, encoding):
        if encoding not in self.parsers:
            self.parsers[encoding] = lxml.etree.HTMLParser(encoding=encoding)
        return self.parsers[encoding]

    def _request_with_retry(self, http_method, uri, kwargs):
        with self.max_requests:
            return self._call_request_with_retry(http_method, uri, kwargs)

    def _call_request_with_retry(self, http_method, uri, kwargs):
        """Send a HTTP request."""
        for retry in range(self.http_retry):
            try:
                return self._request(http_method, uri, kwargs)
            except requests.exceptions.RequestException as exc:
                LOG.warning(
                    'HTTP %d for %s (retry %d)',
                    get_status_code(exc), uri, retry, exc_info=True)
                time.sleep(self.http_retry_base_delay * 2 ** retry)
        return self._request(http_method, uri, kwargs)

    def _request(self, http_method, uri, kwargs):
        """Helper for sending a HTTP request."""
        # Session.{get,post,head,...}() do more settings than plain
        # Session.request().  So we don't just call request() here.
        response = http_method(uri, **kwargs)
        response.raise_for_status()
        # A little bit of monkey patching on the response object.
        response.dom = functools.update_wrapper(
            functools.partial(self.dom, response),
            self.dom,
        )
        return response

    def _send(self, request, **kwargs):
        """Wrap session.send()."""
        if LOG.isEnabledFor(logging.DEBUG):
            for name in request.headers:
                LOG.debug('<<< %s: %s', name, request.headers[name])
        response = self._session_send(request, **kwargs)
        if LOG.isEnabledFor(logging.DEBUG):
            for name in response.headers:
                LOG.debug('>>> %s: %s', name, response.headers[name])
        return response
