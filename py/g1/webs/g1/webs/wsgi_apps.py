__all__ = [
    'Application',
    'HttpError',
    'Request',
    'Response',
    'ResponseClosed',
]

import collections.abc
import dataclasses
import enum
import logging
import typing
import urllib.parse

from g1.asyncs.bases import locks
from g1.asyncs.bases import queues
from g1.asyncs.bases import servers
from g1.asyncs.bases import streams
from g1.asyncs.bases import tasks
from g1.bases import contexts
from g1.bases import lifecycles
from g1.bases.assertions import ASSERT

from . import consts

LOG = logging.getLogger(__name__)


class HttpError(Exception):

    @classmethod
    def redirect(cls, status, message, location):
        ASSERT.in_range(status, (300, 400))
        return cls(status, message, {consts.HEADER_LOCATION: location})

    # The headers argument can be either dict or pairs.  Note that while
    # HTTP headers can be duplicated, we still use a dict to represent
    # headers because here we are a producer rather than a parser of
    # HTTP headers.
    def __init__(self, status, message, headers=None, content=b''):
        super().__init__(message)
        self.status = ASSERT.in_range(_cast_status(status), (300, 600))
        self.headers = ASSERT.predicate(
            dict(headers) if headers is not None else {},
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

    #
    # NOTE: Handlers are expected to mutate context content directly.
    # Although the context object support hierarchical interface (and
    # thus no mutation on the content), mutation is preferred because,
    # with mutation, handlers do not have to be fitted into a hierarchy,
    # and sibling handlers may see context changes made by each other.
    #
    # Of course, when a handler passes the context to a non-handler, and
    # you are worried that the non-handler code might "corrupt" the
    # context content, the handler may use context's hierarchy interface
    # to isolate context changes made by the non-handler code.
    #
    context: contexts.Context

    def __post_init__(self):
        lifecycles.monitor_object_aliveness(self)
        lifecycles.monitor_object_aliveness(
            self.context, key=(type(self), 'context')
        )

    def get_header(self, name, default=None):
        environ_name = 'HTTP_' + name.replace('-', '_').upper()
        return self.environ.get(environ_name, default)

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


class ResponseClosed(ValueError):
    """When writing to a closed response object.

    This inherits from ValueError as file-like objects raises ValueError
    when writing to a closed file.
    """


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

    def commit(self):
        return self._private.commit()

    async def write(self, data):
        return await self._private.write(data)

    def sendfile(self, file):
        return self._private.sendfile(file)

    def close(self):
        return self._private.close()


@enum.unique
class _SendMechanisms(enum.Enum):
    UNDECIDED = enum.auto()
    SEND = enum.auto()
    SENDFILE = enum.auto()


class _Response:
    """Response object.

    A response is in one of three states:

    * UNCOMMITTED:
        A response starts in this state, and transitions to COMMITTED if
        `commit` is called, and to CLOSED if `close` is called.  Users
        may set status code and headers and write to the response body
        when response is in this state.

    * COMMITTED:
        A response transitions to CLOSED if `close` is called.  In this
        state, users may only write to the response body, may read
        response data.

    * CLOSED:
        A response is read-only in this state.
    """

    class Headers(collections.abc.MutableMapping):

        def __init__(self, is_uncommitted):
            self._is_uncommitted = is_uncommitted
            self._headers = {}

        def __len__(self):
            return len(self._headers)

        def __iter__(self):
            return iter(self._headers)

        def __getitem__(self, header):
            return self._headers[header]

        def __setitem__(self, header, value):
            ASSERT.true(self._is_uncommitted())
            ASSERT.isinstance(header, str)
            ASSERT.isinstance(value, str)
            self._headers[header] = value

        def __delitem__(self, header):
            ASSERT.true(self._is_uncommitted())
            del self._headers[header]

    @classmethod
    def _make_precommit(cls):
        precommit = streams.BytesStream()
        lifecycles.monitor_object_aliveness(precommit, key=(cls, 'precommit'))
        return precommit

    def __init__(self, start_response, is_sendfile_supported):
        self._start_response = start_response

        self._status = consts.Statuses.OK
        self.headers = self.Headers(self.is_uncommitted)

        self._precommit = self._make_precommit()
        # Set capacity to 1 to prevent excessive buffering.
        self._body = queues.Queue(capacity=1)
        self.file = None

        self._send_mechanism = _SendMechanisms.UNDECIDED
        self._send_mechanism_decided = locks.Event()

        lifecycles.monitor_object_aliveness(self)

        if not is_sendfile_supported:
            self._set_send_mechanism(_SendMechanisms.SEND)

    def is_uncommitted(self):
        return self._precommit is not None and not self._body.is_closed()

    def reset(self):
        """Reset response status, headers, and content."""
        ASSERT.true(self.is_uncommitted())

        self._status = consts.Statuses.OK

        # Do NOT call `self.headers.clear`, but replace it with a new
        # headers object instead because application code might still
        # keep a reference to the old headers object, and clearing it
        # could cause confusing results.
        self.headers = self.Headers(self.is_uncommitted)

        # It is safe to replace `_precommit` on uncommitted response.
        self._precommit.close()
        self._precommit = self._make_precommit()

    def commit(self):
        """Commit the response.

        Once the response is committed, you cannot change its status or
        headers, but the response is not done yet, and you may continue
        writing its content until it is closed.
        """
        if not self.is_uncommitted():
            return

        self._start_response(
            self._format_status(self._status),
            list(self.headers.items()),
        )

        # Non-closed BytesStream returns None when it is empty.
        data = self._precommit.read_nonblocking()
        if data is not None:
            self._body.put_nonblocking(data)

        self._precommit.close()
        self._precommit = None

    def cancel(self, exc):
        status = consts.Statuses.SERVICE_UNAVAILABLE
        headers = [(consts.HEADER_RETRY_AFTER, '60')]

        if self.is_uncommitted():
            self.reset()
            self.status = status
            self.headers.update(headers)
            return

        self._body.close(graceful=False)
        self._start_response(
            self._format_status(status),
            headers,
            (exc.__class__, exc, exc.__traceback__),
        )

    def err_after_commit(self, exc):
        """Record exception raised after commit.

        This first closes the response, dropping remaining body data,
        and then calls start_response with HTTP 5xx and exc_info.  If
        the WSGI server has not yet started sending response, it resets
        the response to HTTP 500; otherwise it re-raises the exception.
        """
        ASSERT.false(self.is_uncommitted())
        self._body.close(graceful=False)
        self._start_response(
            self._format_status(consts.Statuses.INTERNAL_SERVER_ERROR),
            [],
            (exc.__class__, exc, exc.__traceback__),
        )

    @staticmethod
    def _format_status(status):
        return '{status.value} {status.phrase}'.format(status=status)

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, status):
        ASSERT.true(self.is_uncommitted())
        self._status = _cast_status(status)

    async def read(self):
        try:
            return await self._body.get()
        except queues.Closed:
            return b''

    async def write(self, data):
        if self._body.is_closed():
            raise ResponseClosed('response is closed')
        ASSERT.is_not(self._send_mechanism, _SendMechanisms.SENDFILE)
        self._set_send_mechanism(_SendMechanisms.SEND)
        if not data:
            return 0
        if self.is_uncommitted():
            return self._precommit.write_nonblocking(data)
        try:
            await self._body.put(data)
        except queues.Closed:
            # Re-raise ValueError like other file-like classes.
            raise ResponseClosed('response is closed') from None
        return len(data)

    def sendfile(self, file):
        if self._body.is_closed():
            raise ResponseClosed('response is closed')
        # sendfile can be called only once.
        ASSERT.is_(self._send_mechanism, _SendMechanisms.UNDECIDED)
        ASSERT.not_none(file)
        self._set_send_mechanism(_SendMechanisms.SENDFILE)
        self.file = file

    def close(self):
        try:
            self.commit()
        finally:
            # Although unlikely, add `finally` in case commit errs out.
            self._send_mechanism_decided.set()
            self._body.close()

    def _set_send_mechanism(self, mechanism):
        ASSERT.is_not(mechanism, _SendMechanisms.UNDECIDED)
        self._send_mechanism = mechanism
        self._send_mechanism_decided.set()

    async def wait_send_mechanism_decided(self):
        await self._send_mechanism_decided.wait()


class Application:

    def __init__(self, handler):
        self._handler = handler
        self._handler_queue = tasks.CompletionQueue()

    async def serve(self):
        await servers.supervise_server(self._handler_queue, ())

    def shutdown(self):
        self._handler_queue.close()

    async def __call__(self, environ, start_response):
        ASSERT.false(self._handler_queue.is_closed())

        request = Request(environ=environ, context=contexts.Context())

        file_wrapper = environ.get('wsgi.file_wrapper')
        response = _Response(start_response, file_wrapper is not None)

        # Handler task may linger on after application completes.  You
        # could do tricks with this feature.
        self._handler_queue.spawn(self._run_handler(request, response))

        await response.wait_send_mechanism_decided()
        if response.file is None:
            return self._iter_content(response)
        else:
            return file_wrapper(response.file)

    async def _run_handler(self, request, response):
        try:
            await self._handler(request, Response(response))
        except ResponseClosed:
            pass
        except Exception as exc:
            await self._on_handler_error(request, response, exc)
        except BaseException as exc:
            # Most likely a task cancellation, not really an error.
            response.cancel(exc)
            raise
        finally:
            response.close()

    @staticmethod
    async def _on_handler_error(request, response, exc):
        if not response.is_uncommitted():
            response.err_after_commit(exc)
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
                '%s %s%s%s context=%r: '
                'handler crashes before commits response',
                *log_args,
                request.context,
                exc_info=exc,
            )
            # TODO: What headers should we set in this case?
            response.status = consts.Statuses.INTERNAL_SERVER_ERROR
            return

        log_args += (exc.status.value, exc.status.phrase)
        if 300 <= exc.status < 400:
            LOG.debug(
                '%s %s%s%s -> %d %s %s ; reason: %s', \
                *log_args, exc.location, exc
            )
        elif 400 <= exc.status < 500:
            LOG.info('%s %s%s%s -> %d %s ; reason: %s', *log_args, exc)
        elif exc.status == 503:
            LOG.warning('%s %s%s%s -> %d %s ; reason: %s', *log_args, exc)
        else:
            LOG.warning('%s %s%s%s -> %d %s', *log_args, exc_info=exc)

        response.status = exc.status
        response.headers.update(exc.headers)
        if exc.content:
            await response.write(exc.content)

    @staticmethod
    async def _iter_content(response):
        try:
            while True:
                data = await response.read()
                if not data:
                    break
                yield data
        finally:
            # There are two code paths that may reach here.  One is when
            # handler returns, and _run_handler closes the response.
            # The other is when this async generator is cancelled.  In
            # the latter case, you must call `response.close` to notify
            # handler.
            response.close()


def _cast_status(status):
    return consts.Statuses(status)  # pylint: disable=no-value-for-parameter
