"""HTTP client library."""

__all__ = [
    'HttpClient',
]

import functools
import logging
import time

import lxml.etree
import requests

from startup import startup

from garage import ARGS
from garage import PARSE
from garage import PARSER
from garage.http.error import HttpError


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/40.0.2214.111 Safari/537.36'
)


HTTP_RETRY = 0
HTTP_RETRY_BASE_DELAY = 1


@startup
def add_arguments(parser: PARSER) -> PARSE:
    group = parser.add_argument_group(__name__)
    group.add_argument(
        '--http-retry', type=int, default=HTTP_RETRY,
        help='set number of retries on http error (default %(default)s)')
    group.add_argument(
        '--http-retry-base-delay', type=int, default=HTTP_RETRY_BASE_DELAY,
        help='set base delay between retries which grows exponentially '
             '(default %(default)s seconds)')


@startup
def configure_http_retry(args: ARGS):
    global HTTP_RETRY, HTTP_RETRY_BASE_DELAY
    HTTP_RETRY = args.http_retry
    HTTP_RETRY_BASE_DELAY = args.http_retry_base_delay


class HttpClient:
    """Wrapper of requests.Session object."""

    @staticmethod
    def make():
        LOG.info('create http client with: agent=%r, retry=%d',
                 USER_AGENT, HTTP_RETRY)
        return HttpClient(
            headers={'User-Agent': USER_AGENT},
            http_retry=HTTP_RETRY,
            http_retry_base_delay=HTTP_RETRY_BASE_DELAY,
        )

    def __init__(self, *, headers, http_retry, http_retry_base_delay):
        self.session = requests.Session()
        self.session.headers.update(headers)
        self.parsers = {}
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

    def form(self, uri, **kwargs):
        """Post an HTML form interactively."""
        tree = self.get(uri, **kwargs).dom()
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
        yield self.post(action_uri, data=data)

    def dom(self, response):
        """Return a DOM object of the contents."""
        parser = self._get_parser(response.encoding)
        return lxml.etree.fromstring(response.content, parser)

    def _get_parser(self, encoding):
        if encoding not in self.parsers:
            self.parsers[encoding] = lxml.etree.HTMLParser(encoding=encoding)
        return self.parsers[encoding]

    def _request_with_retry(self, http_method, uri, kwargs):
        """Send a HTTP request."""
        for retry in range(self.http_retry):
            try:
                return self._request(http_method, uri, kwargs)
            except requests.exceptions.RequestException as exc:
                if exc.response is not None:
                    status_code = exc.response.status_code
                else:
                    status_code = -1
                LOG.warning(
                    'HTTP %d for %s (retry %d)',
                    status_code, uri, retry,
                    exc_info=True)
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
