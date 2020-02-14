__all__ = [
    'Application',
    'HttpError',
    'Request',
    'Response',
]

import collections.abc
import dataclasses
import logging
import typing
import urllib.parse

from g1.asyncs import servers
from g1.asyncs.bases import locks
from g1.asyncs.bases import streams
from g1.asyncs.bases import tasks
from g1.bases.assertions import ASSERT

from . import consts

LOG = logging.getLogger(__name__)


class HttpError(Exception):

    @classmethod
    def redirect(cls, status, message, location):
        ASSERT.in_range(status, (300, 400))
        return cls(status, message, {consts.HEADER_LOCATION: location})

    def __init__(self, status, message, headers=None, content=b''):
        super().__init__(message)
        self.status = ASSERT.in_range(_cast_status(status), (300, 600))
        self.headers = ASSERT.predicate(
            headers if headers is not None else {},
            lambda hdrs: all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in hdrs.items()
            ),
        )
        self.content = ASSERT.isinstance(content, bytes)

    @property
    def location(self):
        return self.headers.get(consts.HEADER_LOCATION)


@dataclasses.dataclass(frozen=True)
class Request:

    environ: typing.Mapping[str, str]
    context: typing.Mapping[str, typing.Any] = \
        dataclasses.field(default_factory=dict)

    @property
    def method(self):
        return self.environ['REQUEST_METHOD']

    @property
    def path_str(self):
        return self.environ['PATH_INFO']

    @property
    def path(self):
        return consts.UrlPath(self.path_str)

    @property
    def query_str(self):
        return self.environ['QUERY_STRING']

    @property
    def query(self):
        return urllib.parse.parse_qs(self.query_str)

    @property
    def query_list(self):
        return urllib.parse.parse_qsl(self.query_str)

    @property
    def content(self):
        return self.environ['wsgi.input']


# A proxy object to expose only public interface.
class Response:

    def __init__(self, private):
        self._private = private

    @property
    def status(self):
        return self._private.status

    @status.setter
    def status(self, status):
        self._private.status = status

    @property
    def headers(self):
        return self._private.headers

    async def write(self, data):
        return await self._private.write(data)

    def write_nonblocking(self, data):
        return self._private.write_nonblocking(data)

    def commit(self):
        return self._private.commit()

    def close(self):
        return self._private.close()


class _Response:

    class Headers(collections.abc.MutableMapping):

        def __init__(self, committed):
            self._committed = committed
            self._headers = {}

        def __len__(self):
            return len(self._headers)

        def __iter__(self):
            return iter(self._headers)

        def __getitem__(self, header):
            return self._headers[header]

        def __setitem__(self, header, value):
            ASSERT.false(self._committed.is_set())
            ASSERT.isinstance(header, str)
            ASSERT.isinstance(value, str)
            self._headers[header] = value

        def __delitem__(self, header):
            ASSERT.false(self._committed.is_set())
            del self._headers[header]

    def __init__(self, start_response):
        self._committed = locks.Event()
        self._closed = False
        self._error_after_commit = None
        self._start_response = start_response
        self._status = consts.Statuses.OK
        self.headers = self.Headers(self._committed)
        self._content = streams.BytesStream()

    def is_committed(self):
        return self._committed.is_set()

    def commit(self):
        """Commit the response.

        Once the response is committed, you cannot change its status or
        headers, but the response is not done yet, and you may continue
        writing its content until it is closed.

        Calling commit and close separately is an advanced technique.
        However I do not know which use case need such technique yet.
        """
        if self.is_committed():
            return
        self._start_response(
            '%d %s' % (self._status.value, self._status.phrase),
            list(self.headers.items()),
        )
        self._committed.set()

    async def wait_committed(self):
        await self._committed.wait()

    def set_error_after_commit(self, exc):
        """Set exception raised after commit but before close.

        A handler should never fail after it commits the response, but
        if it does fail anyway, you should record such mortal sin with
        this method.
        """
        ASSERT.true(self.is_committed() and not self._closed)
        self._error_after_commit = exc
        # We cannot replace ``_content`` here because the response was
        # committed, but this does not matter since we are dealing with
        # error-after-commit.
        self._content.close()

    def raise_for_error_after_commit(self):
        if self._error_after_commit:
            raise self._error_after_commit

    def reset(self):
        """Reset response status, headers, and content."""
        ASSERT.false(self.is_committed())
        self._status = consts.Statuses.OK
        self.headers.clear()
        # It's safe to replace ``_content`` because the response is not
        # committed yet, and ``read`` can only be called after commit.
        self._content.close()
        self._content = streams.BytesStream()

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, status):
        ASSERT.false(self.is_committed())
        self._status = _cast_status(status)

    async def read(self):
        ASSERT.true(self.is_committed())
        return await self._content.read()

    async def write(self, data):
        return await self._content.write(data)

    def write_nonblocking(self, data):
        return self._content.write_nonblocking(data)

    def close(self):
        """Close response content buffer.

        This marks the true end of the response.
        """
        self.commit()
        self._content.close()
        self._closed = True


class Application:

    def __init__(self, handler):
        self._handler = handler
        self._handler_queue = tasks.CompletionQueue()

    async def serve(self):
        await servers.supervise_handlers(self._handler_queue, ())

    def shutdown(self):
        self._handler_queue.close()

    async def __call__(self, environ, start_response):
        ASSERT.false(self._handler_queue.is_closed())
        request = Request(environ=environ)
        response = _Response(start_response)
        # Handler task may linger on after application completes.  You
        # could do tricks with this feature.
        self._handler_queue.spawn(self._run_handler(request, response))
        return self._iter_content(response)

    async def _run_handler(self, request, response):
        try:
            await self._handler(request, Response(response))
        except BaseException as exc:
            self._on_handler_error(request, response, exc)
        finally:
            response.close()

    @staticmethod
    def _on_handler_error(request, response, exc):
        if response.is_committed():
            response.set_error_after_commit(exc)
            return
        response.reset()
        log_args = (
            request.method,
            request.path,
            '?' if request.query_str else '',
            request.query_str,
        )
        if not isinstance(exc, HttpError):
            LOG.error(
                '%s %s%s%s: handler crashes before commits response',
                *log_args,
                exc_info=exc,
            )
            # TODO: What headers should we set in this case?
            response.status = consts.Statuses.INTERNAL_SERVER_ERROR
            return
        log_args += (exc.status.value, exc.status.phrase)
        if 300 <= exc.status < 400:
            LOG.info('%s %s%s%s -> %d %s %s: %s', *log_args, exc.location, exc)
        else:
            LOG.warning('%s %s%s%s -> %d %s', *log_args, exc_info=exc)
        response.status = exc.status
        response.headers.update(exc.headers)
        if exc.content:
            response.write_nonblocking(exc.content)

    @staticmethod
    async def _iter_content(response):
        await response.wait_committed()
        while True:
            data = await response.read()
            if not data:
                break
            yield data
        # Handler crashed after the response is committed.  The only
        # option left is to raise here to notify the http session to
        # reset the stream.
        response.raise_for_error_after_commit()


def _cast_status(status):
    return consts.Statuses(status)  # pylint: disable=no-value-for-parameter
