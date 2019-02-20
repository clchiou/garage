"""Asynchronous HTTP session backed by an executor.

This session class is a very leaky abstraction of ``requests.Session``,
but its interface is deliberately made different from ``requests`` for
the ease of programmatic use cases.
"""

__all__ = [
    'Request',
    'Session',
]

import functools
import itertools
import logging

import lxml.etree

import requests
import requests.cookies

from g1.asyncs.bases import adapters
from g1.asyncs.bases import timers
from g1.bases.assertions import ASSERT
from g1.threads import executors

from . import policies

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

XML_PARSER = lxml.etree.XMLParser()


@functools.lru_cache(maxsize=8)
def get_html_parser(encoding):
    return lxml.etree.HTMLParser(encoding=encoding)


class Session:

    def __init__(
        self,
        *,
        executor=None,
        rate_limit=None,
        retry=None,
    ):
        # If you do not provide an executor, I will just make one for
        # myself, but to save you the effort to shut down the executor,
        # I will also make it daemonic.  This is mostly fine since if
        # the process is exiting, you probably do not care much about
        # unfinished HTTP requests in the executor (if it is not fine,
        # you may always provide an executor to me, and properly shut it
        # down on process exit).
        self.executor = executor or executors.Executor(daemon=True)
        self._session = requests.Session()
        self._rate_limit = rate_limit or policies.unlimited
        self._retry = retry or policies.no_retry

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

    async def send(self, request, **kwargs):
        """Send a request and return a response."""

        # For now ``stream`` and asynchronous does not mix well.
        ASSERT.false(request._kwargs.get('stream'))
        ASSERT.false(kwargs.get('stream'))

        for retry_count in itertools.count():

            await self._rate_limit()

            if retry_count:
                LOG.warning('retry %d times: %r', retry_count, request)

            future = adapters.FutureAdapter(
                self.executor.submit(self.send_blocking, request, **kwargs)
            )
            try:
                return await future.get_result()

            except requests.RequestException as exc:
                backoff = self._retry(retry_count)
                if backoff is None:
                    raise

                if exc.response:
                    status_code = exc.response.status_code
                else:
                    status_code = '???'
                LOG.warning(
                    'http error: status_code=%s, %r',
                    status_code,
                    request,
                    exc_info=exc,
                )

                await timers.sleep(backoff)

    def send_blocking(self, request, **kwargs):
        """Send a request in a blocking manner.

        This does not implement rate limit nor retry.
        """
        LOG.debug('send: %r, kwargs=%r', request, kwargs)

        # ``requests.Session.get`` and friends do a little more than
        # ``requests.Session.request``; so let's use the former.
        method = getattr(self._session, request.method.lower())

        # ``kwargs`` may overwrite ``request._kwargs``.
        final_kwargs = request._kwargs.copy()
        final_kwargs.update(kwargs)

        response = method(request.url, **final_kwargs)
        response.raise_for_status()

        return response


class Request:

    def __init__(self, method, url, **kwargs):
        self.method = method
        self.url = url
        self._kwargs = kwargs

    def __repr__(self):
        return '<%s at %#x: %s %s kwargs=%r>' % (
            self.__class__.__qualname__,
            id(self),
            self.method.upper(),
            self.url,
            self._kwargs,
        )

    @property
    def headers(self):
        return self._kwargs.setdefault('headers', {})


#
# Monkey-patch ``requests.Response``.
#


def html(self, encoding=None, errors=None):
    #
    # The caller intends to handle character encoding error in a way
    # that is different from lxml's (lxml refuses to parse the rest of
    # the document if there is any encoding error in the middle, but it
    # does not report the error either).
    #
    # lxml's strict-but-silent policy is counterproductive because web
    # is full of malformed documents, and it should either be lenient
    # about the error, or raise it to the caller, not a mix of both as
    # it is right now.
    #
    if encoding and errors:
        # So, let's decode the byte string ourselves and do not rely
        # on lxml on that.
        contents = self.content.decode(encoding=encoding, errors=errors)
        parser = get_html_parser(None)
        return lxml.etree.fromstring(contents, parser)

    ASSERT.none(errors)

    parser = get_html_parser(encoding or self.encoding)
    return lxml.etree.fromstring(self.content, parser)


def xml(self):
    return lxml.etree.fromstring(self.content, XML_PARSER)


# Just to make sure we do not accidentally override them.
ASSERT.false(hasattr(requests.Response, 'html'))
ASSERT.false(hasattr(requests.Response, 'xml'))
requests.Response.html = html
requests.Response.xml = xml
