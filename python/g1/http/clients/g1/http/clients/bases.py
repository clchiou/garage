__all__ = [
    'BaseSession',
    'Request',
    'Response',
    'Sender',
]

import functools
import itertools
import json
import logging
import urllib.parse

import lxml.etree
import requests
import requests.adapters
import requests.cookies
import urllib3.exceptions
import urllib3.util.ssl_

from g1.asyncs.bases import adapters
from g1.asyncs.bases import tasks
from g1.asyncs.bases import timers
from g1.bases import classes
from g1.bases import collections as g1_collections
from g1.bases.assertions import ASSERT
from g1.threads import executors

from . import policies
from . import recvfiles

LOG = logging.getLogger(__name__)


class Sender:
    """Request sender with local cache, rate limit, and retry."""

    def __init__(
        self,
        send,
        *,
        cache_size=8,
        circuit_breakers=None,
        rate_limit=None,
        retry=None,
    ):
        self._send = send
        self._cache = g1_collections.LruCache(cache_size)
        self._unbounded_cache = {}
        self._circuit_breakers = circuit_breakers or policies.NO_BREAK
        self._rate_limit = rate_limit or policies.unlimited
        self._retry = retry or policies.no_retry

    async def __call__(self, request, **kwargs):
        """Send a request and return a response.

        If argument ``cache_key`` is not ``None``, session will check
        its cache before sending the request.  For now, we don't support
        setting ``cache_key`` in ``request``.

        ``sticky_key`` is similar to ``cache_key`` except that it refers
        to an unbounded cache (thus the name "sticky").

        If argument ``cache_revalidate`` is evaluated to true, session
        will revalidate the cache entry.

        If argument ``circuit_breaker_key`` is not ``None``, it will
        override the default key (request URL domain name).
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

        circuit_breaker_key = kwargs.pop('circuit_breaker_key', None)
        if circuit_breaker_key is None:
            circuit_breaker_key = urllib.parse.urlparse(request.url).netloc

        breaker = self._circuit_breakers.get(circuit_breaker_key)
        for retry_count in itertools.count():

            # Check rate limit out of the breaker async-with context to
            # avoid adding extra delay in the context so that, when the
            # breaker is in YELLOW state, another request may "go" into
            # the context as soon as the previous one completes.
            await self._rate_limit()

            async with breaker:
                response, backoff = await self._loop_body(
                    request, kwargs, breaker, retry_count
                )
            if response is not None:
                return response

            # Call `sleep` out of the breaker async-with context for the
            # same reason above.
            await timers.sleep(ASSERT.not_none(backoff))

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

    async def _loop_body(self, request, kwargs, breaker, retry_count):
        if retry_count:
            LOG.warning('retry %d times: %r', retry_count, request)
        try:
            response = await self._send(request, **kwargs)

        except (
            requests.RequestException,
            urllib3.exceptions.HTTPError,
        ) as exc:
            status_code = self._get_status_code(exc)
            if status_code is not None and 400 <= status_code < 500:
                # From the perspective of circuit breaker, a 4xx is
                # considered a "success".
                breaker.notify_success()
                # It does not seem to make sense to retry on 4xx errors
                # as our request was explicitly rejected by the server.
                raise

            breaker.notify_failure()

            backoff = self._retry(retry_count)
            if backoff is None:
                raise
            LOG.warning(
                'http error: status_code=%s, request=%r, exc=%r',
                status_code,
                request,
                exc,
            )
            return None, backoff

        except Exception:
            breaker.notify_failure()
            raise

        else:
            breaker.notify_success()
            return response, None

    @staticmethod
    def _get_status_code(exc):
        # requests.Response defines __bool__ that returns to true when
        # status code is less than 400; so we have to explicitly check
        # `is None` here, rather than `if not response:`.
        response = getattr(exc, 'response', None)
        if response is None:
            return None
        return response.status_code


class BaseSession:
    """Base session.

    All this does is backing an HTTP session with an executor; this does
    not provide rate limit nor retry.  You use this as a building block
    for higher level session types.
    """

    _SSL_CONTEXT = urllib3.util.ssl_.create_urllib3_context()
    _SSL_CONTEXT.load_default_certs()

    def __init__(
        self,
        *,
        executor=None,
        num_pools=0,
        num_connections_per_pool=0,
    ):
        # If you do not provide an executor, I will just make one for
        # myself, but to save you the effort to shut down the executor,
        # I will also make it daemonic.  This is mostly fine since if
        # the process is exiting, you probably do not care much about
        # unfinished HTTP requests in the executor (if it is not fine,
        # you may always provide an executor to me, and properly shut it
        # down on process exit).
        self._executor = executor or executors.Executor(daemon=True)

        self._session = requests.Session()

        adapter_kwargs = {}
        if num_pools > 0:
            adapter_kwargs['pool_connections'] = num_pools
        if num_connections_per_pool > 0:
            adapter_kwargs['pool_maxsize'] = num_pools
        if adapter_kwargs:
            LOG.info(
                'config session: num_pools=%d num_connections_per_pool=%d',
                num_pools,
                num_connections_per_pool,
            )
            self._session.mount(
                'https://', requests.adapters.HTTPAdapter(**adapter_kwargs)
            )
            self._session.mount(
                'http://', requests.adapters.HTTPAdapter(**adapter_kwargs)
            )

        # Make all connections share one SSL context to reduce memory
        # footprint.
        (self._session.get_adapter('https://').poolmanager\
         .connection_pool_kw['ssl_context']) = self._SSL_CONTEXT

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
        priority = kwargs.pop('priority', None)
        if priority is None:
            future = self._executor.submit(
                self.send_blocking, request, **kwargs
            )
        else:
            LOG.debug(
                'send: priority=%r, %r, kwargs=%r', priority, request, kwargs
            )
            future = self._executor.submit_with_priority(
                priority, self.send_blocking, request, **kwargs
            )
        future.set_finalizer(lambda response: response.close())
        return await adapters.FutureAdapter(future).get_result()

    def send_blocking(self, request, **kwargs):
        """Send a request in a blocking manner.

        If ``stream`` is set to true, we will return the original
        response object, and will NOT copy-then-close it to our response
        class.  In this case, the caller is responsible for closing the
        response object.

        This does not implement rate limit nor retry.
        """
        LOG.debug('send: %r, kwargs=%r', request, kwargs)

        # ``requests.Session.get`` and friends do a little more than
        # ``requests.Session.request``; so let's use the former.
        method = getattr(self._session, request.method.lower())

        # ``kwargs`` may overwrite ``request._kwargs``.
        final_kwargs = request._kwargs.copy()
        final_kwargs.update(kwargs)

        source = method(request.url, **final_kwargs)
        stream = final_kwargs.get('stream')
        if stream:
            response = source
        else:
            try:
                response = Response(
                    source,
                    source.content,  # Force consuming the content.
                )
            finally:
                source.close()

        try:
            response.raise_for_status()
        except Exception:
            # Force consuming the content.  In case caller sets
            # stream=True, this ensures that exc.response.content is not
            # empty.
            response.content  # pylint: disable=pointless-statement
            # On error, close the original response for the caller since
            # the caller usually forgets to do this.
            response.close()
            raise

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

    def copy(self):
        return Request(self.method, self.url, **self._kwargs)


class Response:
    """HTTP response.

    This class provides an interface that is mostly compatible with
    ``requests`` Response class.

    We do this because if a ``requests`` Response object is not closed
    (doc does not seem to suggest explicitly closing responses?), it
    will not release the connection back to the connection pool.
    """

    def __init__(self, source, content, *, _copy_history=True):
        """Make a "copy" from a ``requests`` Response object.

        Note that this consumes the content of the ``source`` object,
        which forces ``source`` to read the whole response body from the
        server (and so we do not need to do this in the Sender class).
        """
        self._content = content

        self.status_code = source.status_code
        self.headers = source.headers
        self.url = source.url
        if _copy_history:
            self.history = [
                Response(
                    r,
                    # TODO: Should we load r.content?
                    None,
                    # TODO: In some rare cases, history seems to have
                    # loops.  We probably should try to detect loops,
                    # but for now, let us only go into one level of the
                    # history.
                    _copy_history=False,
                ) for r in source.history
            ]
        else:
            # Make it non-iterable so that if user (accidentally)
            # iterates this, it will err out.
            self.history = None
        self.encoding = source.encoding
        self.reason = source.reason
        self.cookies = source.cookies
        self.elapsed = source.elapsed
        # We do not copy source.request for now.

    __repr__ = classes.make_repr(
        'status_code={self.status_code} url={self.url}',
    )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        # Nothing to do here; just for interface compatibility.
        pass

    def raise_for_status(self):
        if not 400 <= self.status_code < 600:
            return
        if isinstance(self.reason, bytes):
            # Try utf-8 first because some servers choose to localize
            # their reason strings.  If the string is not utf-8, fall
            # back to iso-8859-1.
            try:
                reason = self.reason.decode('utf-8')
            except UnicodeDecodeError:
                reason = self.reason.decode('iso-8859-1')
        else:
            reason = self.reason
        raise requests.HTTPError(
            '%s %s error: %s %s' % (
                self.status_code,
                'client' if 400 <= self.status_code < 500 else 'server',
                reason,
                self.url,
            ),
            response=self,
        )

    @property
    def content(self):
        return self._content

    @classes.memorizing_property
    def text(self):
        # NOTE: Unlike ``requests``, we do NOT fall back to
        # auto-detected encoding.
        return self.content.decode(ASSERT.not_none(self.encoding))

    def json(self, **kwargs):
        """Parse response as a JSON document."""
        return json.loads(self.content, **kwargs)

    #
    # Interface that ``requests.Response`` does not provide (we will
    # monkey-patch it below).
    #

    def html(self, encoding=None, errors=None):
        """Parse response as an HTML document.

        Caller may pass ``encoding`` and ``errors`` to instructing us
        how to decode response content.  This is useful because lxml's
        default is to **silently** skip the rest of the document when
        there is any encoding error in the middle.

        lxml's strict-but-silent policy is counterproductive because web
        is full of malformed documents, and it should either be lenient
        about the error, or raise it to the caller, not a mix of both as
        it is right now.
        """
        if encoding and errors:
            string = self.content.decode(encoding=encoding, errors=errors)
            parser = _get_html_parser(None)
        else:
            ASSERT.none(errors)
            string = self.content
            parser = _get_html_parser(
                encoding or ASSERT.not_none(self.encoding)
            )
        # Check whether fromstring returns None because apparently
        # HTMLParser is more lenient than XMLParser and may cause
        # fromstring to return None on some malformed HTML input.
        return ASSERT.not_none(lxml.etree.fromstring(string, parser))

    def xml(self):
        """Parse response as an XML document."""
        return lxml.etree.fromstring(self.content, _XML_PARSER)


@functools.lru_cache(maxsize=8)
def _get_html_parser(encoding):
    return lxml.etree.HTMLParser(encoding=encoding)


_XML_PARSER = lxml.etree.XMLParser()

#
# Monkey-patch ``requests.Response``.
#

# Just to make sure we do not accidentally override them.
ASSERT.false(hasattr(requests.Response, 'recvfile'))
requests.Response.recvfile = recvfiles.recvfile
ASSERT.false(hasattr(requests.Response, 'html'))
requests.Response.html = Response.html
ASSERT.false(hasattr(requests.Response, 'xml'))
requests.Response.xml = Response.xml
