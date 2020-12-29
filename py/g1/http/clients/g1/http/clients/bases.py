__all__ = [
    'BaseSession',
    'Request',
    'Sender',
]

import functools
import itertools
import logging

import lxml.etree
import requests
import requests.cookies
import urllib3.exceptions

from g1.asyncs.bases import adapters
from g1.asyncs.bases import tasks
from g1.asyncs.bases import timers
from g1.bases import classes
from g1.bases import collections as g1_collections
from g1.bases.assertions import ASSERT
from g1.threads import executors

from . import policies

LOG = logging.getLogger(__name__)


class Sender:
    """Request sender with local cache, rate limit, and retry."""

    def __init__(self, send, *, cache_size=8, rate_limit=None, retry=None):
        self._send = send
        self._cache = g1_collections.LruCache(cache_size)
        self._unbounded_cache = {}
        self._rate_limit = rate_limit or policies.unlimited
        self._retry = retry or policies.no_retry

    async def __call__(self, request, **kwargs):
        """Send a request and return a response.

        If argument ``cache_key`` is not ``None``, session will check
        its cache before sending the request.  For now, we don't support
        setting ``cache_key`` in ``request``.

        ``sticky_key`` is similar to ``cache_key`` except that it refers
        to an unbounded cache (thus the name "sticky").

        If argument ``cache_revalidate`` is evaludated to true, session
        will revalidate the cache entry.
        """
        cache_key = kwargs.pop('cache_key', None)
        sticky_key = kwargs.pop('sticky_key', None)
        cache_revalidate = kwargs.pop('cache_revalidate', None)
        if cache_key is not None and sticky_key is not None:
            raise AssertionError(
                'expect at most one: cache_key=%r, sticky_key=%r' %
                (cache_key, sticky_key)
            )
        if cache_key is not None:
            return await self._try_cache(
                self._cache,
                cache_key,
                cache_revalidate,
                request,
                kwargs,
            )
        if sticky_key is not None:
            return await self._try_cache(
                self._unbounded_cache,
                sticky_key,
                cache_revalidate,
                request,
                kwargs,
            )

        for retry_count in itertools.count():
            await self._rate_limit()
            if retry_count:
                LOG.warning('retry %d times: %r', retry_count, request)
            try:
                return await self._send(request, **kwargs)
            except (
                requests.RequestException,
                urllib3.exceptions.HTTPError,
            ) as exc:
                backoff = self._retry(retry_count)
                if backoff is None:
                    raise
                if getattr(exc, 'response', None):
                    status_code = exc.response.status_code
                    # It does not seem to make sense to retry on 4xx
                    # errors since our request was explicitly rejected
                    # by the server.
                    if 400 <= status_code < 500:
                        raise
                else:
                    status_code = None
                LOG.warning(
                    'http error: status_code=%s, request=%r, exc=%r',
                    status_code,
                    request,
                    exc,
                )
                await timers.sleep(backoff)
        ASSERT.unreachable('retry loop should not break')

    async def _try_cache(self, cache, key, revalidate, request, kwargs):
        task = cache.get(key)
        if task is None:
            task = cache[key] = tasks.spawn(self(request, **kwargs))
            result = 'miss'
        elif revalidate:
            task = cache[key] = tasks.spawn(self(request, **kwargs))
            result = 'revalidate'
        else:
            result = 'hit'
        LOG.debug(
            'send: cache %s: key=%r, %r, kwargs=%r', \
            result, key, request, kwargs,
        )
        # Here is a risk that, if all task waiting for this task get
        # cancelled before this task completes, this task might not
        # be joined, but this risk is probably too small.
        return await task.get_result()


class BaseSession:
    """Base session.

    All this does is backing an HTTP session with an executor; this does
    not provide rate limit nor retry.  You use this as a building block
    for higher level session types.
    """

    def __init__(self, executor=None):
        # If you do not provide an executor, I will just make one for
        # myself, but to save you the effort to shut down the executor,
        # I will also make it daemonic.  This is mostly fine since if
        # the process is exiting, you probably do not care much about
        # unfinished HTTP requests in the executor (if it is not fine,
        # you may always provide an executor to me, and properly shut it
        # down on process exit).
        self._executor = executor or executors.Executor(daemon=True)
        self._session = requests.Session()

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
        """Send an HTTP request and return a response.

        If argument ``priority`` is not ``None``, the request is sent
        with priority (this requires ``PriorityExecutor``).  For now, we
        do not support setting ``priority`` in ``request``.
        """
        # For now ``stream`` and asynchronous does not mix well.
        ASSERT.false(request._kwargs.get('stream'))
        ASSERT.false(kwargs.get('stream'))
        priority = kwargs.pop('priority', None)
        if priority is None:
            future = self._executor.submit(
                self._send_blocking, request, kwargs
            )
        else:
            LOG.debug(
                'send: priority=%r, %r, kwargs=%r', priority, request, kwargs
            )
            future = self._executor.submit_with_priority(
                priority, self._send_blocking, request, kwargs
            )
        return await adapters.FutureAdapter(future).get_result()

    def _send_blocking(self, request, kwargs):
        response = self.send_blocking(request, **kwargs)
        # Force consuming contents in an executor thread (since you
        # should not do this in an asynchronous task).
        response.content  # pylint: disable=pointless-statement
        return response

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

    __repr__ = classes.make_repr(
        '{method} {self.url} kwargs={self._kwargs!r}',
        method=lambda self: self.method.upper(),
    )

    @property
    def headers(self):
        return self._kwargs.setdefault('headers', {})


#
# Monkey-patch ``requests.Response``.
#


@functools.lru_cache(maxsize=8)
def get_html_parser(encoding):
    return lxml.etree.HTMLParser(encoding=encoding)


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


XML_PARSER = lxml.etree.XMLParser()


def xml(self):
    return lxml.etree.fromstring(self.content, XML_PARSER)


# Just to make sure we do not accidentally override them.
ASSERT.false(hasattr(requests.Response, 'html'))
ASSERT.false(hasattr(requests.Response, 'xml'))
requests.Response.html = html
requests.Response.xml = xml
