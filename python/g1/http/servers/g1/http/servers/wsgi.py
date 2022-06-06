"""Asynchronous WSGI Server/Gateway implementation."""

__all__ = [
    'FileWrapper',
    'HttpSession',
]

import collections
import enum
import http
import io
import itertools
import logging
import os
import re
import socket

from g1.asyncs.bases import locks
from g1.asyncs.bases import queues
from g1.asyncs.bases import streams
from g1.asyncs.bases import tasks
from g1.asyncs.bases import timers
from g1.bases.assertions import ASSERT

LOG = logging.getLogger(__name__)


class _SessionExit(Exception):
    """Exit a HTTP session (not necessary due to errors)."""


class FileWrapper:

    def __init__(self, file, block_size=8192):
        del block_size  # Unused.
        self._file = file

    def _transfer(self):
        """Transfer ownership of the wrapped file."""
        file, self._file = self._file, None
        return file

    def close(self):
        if self._file is not None:
            self._file.close()


class HttpSession:

    # TODO: Make these configurable.
    _KEEP_ALIVE_IDLE_TIMEOUT = 8

    # A session may stay longer even when the number of requests exceeds
    # this number if the WSGI application explicitly set Keep-Alive in
    # response headers.
    #
    # TODO: Make these configurable.
    _MAX_NUM_REQUESTS_PER_SESSION = 1024

    _KEEP_ALIVE = (b'Connection', b'keep-alive')
    _NOT_KEEP_ALIVE = (b'Connection', b'close')

    _EXIT_EXC_TYPES = (
        _SessionExit,
        socket.timeout,
        ConnectionResetError,
        BrokenPipeError,
    )

    def __init__(self, sock, application, base_environ):
        self._sock = sock
        self._application = application
        self._request_queue = _RequestQueue(self._sock, base_environ)
        self._response_queue = _ResponseQueue(self._sock)

    async def __call__(self):
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with self._sock:
            try:
                for num_requests in itertools.count(1):
                    await self._handle_request(
                        await self._get_request(),
                        num_requests < self._MAX_NUM_REQUESTS_PER_SESSION,
                    )
            except self._EXIT_EXC_TYPES as exc:
                LOG.debug('exit session due to: %r', exc)

    async def _get_request(self):
        try:
            with timers.timeout_after(self._KEEP_ALIVE_IDLE_TIMEOUT):
                environ = await self._request_queue.get()
        except _RequestError as exc:
            LOG.warning('invalid request: %s %s', exc.status, exc)
            await self._put_short_response(exc.status, False)
            raise _SessionExit from None
        except timers.Timeout:
            LOG.debug('keep-alive idle timeout')
            raise _SessionExit from None
        if environ is None:
            raise _SessionExit
        return environ

    async def _handle_request(self, environ, keep_alive):
        # Check if client disables Keep-Alive explicitly.
        connection = environ.get('HTTP_CONNECTION')
        if connection is not None:
            keep_alive = 'keep-alive' in connection.lower()

        # At the moment we do not check any expectations (except those
        # already in _RequestQueue), and just return HTTP 100 here.
        if environ.get('HTTP_EXPECT', '').lower() == '100-continue':
            await self._put_short_response(
                http.HTTPStatus.CONTINUE, keep_alive
            )
            if not keep_alive:
                raise _SessionExit
            return

        context = _ApplicationContext()
        async with tasks.joining(
            tasks.spawn(self._send_response(context, environ, keep_alive)),
            always_cancel=True,
            log_error=False,  # We handle and log error below.
        ) as send_task, tasks.joining(
            tasks.spawn(self._run_application(context, environ)),
            always_cancel=True,
            log_error=False,  # We handle and log error below.
        ) as run_task:
            async for task in tasks.as_completed([send_task, run_task]):
                try:
                    task.get_result_nonblocking()
                except self._EXIT_EXC_TYPES:
                    raise
                except Exception:
                    if self._response_queue.has_begun():
                        LOG.exception(
                            'task crash after response starts sending: %r',
                            task,
                        )
                        raise _SessionExit from None
                    LOG.warning(
                        'task crash before response starts sending: %r',
                        task,
                        exc_info=True,
                    )
                    await self._put_short_response(
                        http.HTTPStatus.INTERNAL_SERVER_ERROR, keep_alive
                    )
                    if not keep_alive:
                        raise _SessionExit from None
                    break

    async def _run_application(self, context, environ):
        body = await self._application(environ, context.start_response)
        try:
            if isinstance(body, FileWrapper):
                # TODO: Implement PEP 333's requirement of falling back
                # to normal iterable handling loop below when body._file
                # is not a regular file.
                context.sendfile(body._transfer())
                # To unblock _send_response task.
                context.end_body_chunks()
                return

            if hasattr(body, '__aiter__'):
                async for chunk in body:
                    await context.put_body_chunk(chunk)
            else:
                for chunk in body:
                    await context.put_body_chunk(chunk)
            #
            # Only call `end_body_chunks` on success.  We do this to fix
            # this corner case:
            #
            # * Let us assume that:
            #   1. self._application has not yet called start_response.
            #   2. self._application further spawns a handler task that
            #      will eventually call start_response.
            #
            # * When `body` iterator errs out, or _run_application task
            #   gets cancelled, if end_body_chunks is called (which
            #   should not), then _send_response task is unblocked and
            #   calls context.commit.
            #
            # * Eventually, the handler task calls start_response.
            #   Because context.commit has been called, start_response
            #   errs out, causing the handler task to err out.
            #
            # This corner case produces very confusing handler task
            # errors, sometimes **lots** of them when the process is
            # shutting down and tasks are getting cancelled.
            #
            # NOTE: This will NOT cause _send_response task being
            # blocked on get_body_chunk forever because _handle_request
            # cancels _send_response when _run_application errs out.
            #
            context.end_body_chunks()
        finally:
            if hasattr(body, 'close'):
                body.close()

    async def _send_response(self, context, environ, keep_alive):
        try:
            return await self._do_send_response(context, environ, keep_alive)
        except timers.Timeout:
            LOG.debug('send/sendfile timeout')
            raise _SessionExit from None
        finally:
            if context.file is not None:
                context.file.close()

    async def _do_send_response(self, context, environ, keep_alive):
        # Start sending status and headers after we receive the first
        # chunk so that user has a chance to call start_response again
        # to reset status and headers.
        chunks = [await context.get_body_chunk()]
        context.commit()

        has_connection_header = False
        content_length = None
        for key, value in context.headers:
            if key.lower() == b'connection':
                has_connection_header = True
                keep_alive = b'keep-alive' in value.lower()
            if key.lower() == b'content-length':
                content_length = int(value)

        if not has_connection_header:
            context.headers.append(
                self._KEEP_ALIVE if keep_alive else self._NOT_KEEP_ALIVE
            )

        if content_length is None:
            if context.file is None:
                while chunks[-1]:
                    chunks.append(await context.get_body_chunk())
                body_size = sum(map(len, chunks))
            else:
                body_size = os.fstat(context.file.fileno()).st_size
            context.headers.append((
                b'Content-Length',
                b'%d' % body_size,
            ))
        else:
            body_size = len(chunks[0])

        omit_body = self._should_omit_body(context.status, environ)
        if omit_body:
            chunks.clear()

        await self._response_queue.begin(context.status, context.headers)

        # TODO: When body chunks or context.file is actually larger than
        # Content-Length provided by the caller, we will still send the
        # extra data to the client, and then err out.  Maybe,
        # alternatively, we should not send the extra data (but still
        # err out)?
        if context.file is None:
            for chunk in chunks:
                if not omit_body:
                    await self._response_queue.put_body_chunk(chunk)
            chunks.clear()
            while True:
                chunk = await context.get_body_chunk()
                if not chunk:
                    break
                if not omit_body:
                    await self._response_queue.put_body_chunk(chunk)
                body_size += len(chunk)
        else:
            if not omit_body:
                body_size = await self._response_queue.sendfile(context.file)

        self._response_queue.end()

        if (
            not omit_body and content_length is not None
            and content_length != body_size
        ):
            LOG.error(
                'Content-Length set to %d but body size is %d: environ=%r',
                content_length,
                body_size,
                environ,
            )
            raise _SessionExit

        if not keep_alive:
            raise _SessionExit

    @staticmethod
    def _should_omit_body(status, environ):
        """Return true if response body should be omitted.

        It is omitted for these cases:
        * RFC7230: 3.3. 1xx, 204 No Content, 304 Not Modified.
        * RFC7231: 6.3.6. 205 Reset Content.
        * HEAD method.
        """
        return (\
            100 <= status < 200 or
            status in (
                http.HTTPStatus.NO_CONTENT,
                http.HTTPStatus.RESET_CONTENT,
                http.HTTPStatus.NOT_MODIFIED,
            ) or
            environ.get('REQUEST_METHOD') == 'HEAD'
        )

    async def _put_short_response(self, status, keep_alive):
        await self._response_queue.begin(
            status,
            [self._KEEP_ALIVE if keep_alive else self._NOT_KEEP_ALIVE],
        )
        self._response_queue.end()


class _RequestError(Exception):
    """Raised by _RequestQueue or _RequestBuffer."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class _TooLong(Exception):
    pass


class _RequestQueue:

    def __init__(self, sock, base_environ):
        self._request_buffer = _RequestBuffer(sock)
        self._base_environ = base_environ

    _MAX_NUM_HEADERS = 128

    async def get(self):
        """Return the next request or None at the end."""
        try:
            line = await self._request_buffer.readline_decoded()
        except _TooLong as exc:
            raise _RequestError(
                http.HTTPStatus.REQUEST_URI_TOO_LONG,
                str(exc),
            ) from None
        if not line:
            return None

        # WSGI requires that the environ argument must be a built-in
        # Python dictionary.
        environ = dict(self._base_environ)

        self._parse_request_line(line, environ)

        headers = collections.defaultdict(list)
        num_headers = 0
        while True:
            try:
                line = await self._request_buffer.readline_decoded()
            except _TooLong as exc:
                raise _RequestError(
                    http.HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE,
                    str(exc),
                ) from None
            if line in ('', '\r\n'):
                break
            if num_headers >= self._MAX_NUM_HEADERS:
                raise _RequestError(
                    http.HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE,
                    'number of request headers exceeds %d' %
                    self._MAX_NUM_HEADERS,
                )
            name, value = self._parse_request_header(line)
            headers[name].append(value)
            num_headers += 1
        for name, values in headers.items():
            environ[name] = ','.join(values)

        content_length = environ.get('CONTENT_LENGTH')
        if content_length is not None:
            try:
                content_length = int(content_length, base=10)
            except ValueError:
                raise _RequestError(
                    http.HTTPStatus.BAD_REQUEST,
                    'invalid request Content-Length: %r' % content_length,
                ) from None

        request_body = streams.BytesStream()
        if content_length is not None:
            # TODO: Set the limit to 64K for now, but we should rewrite
            # this to NOT load the entire request body into the memory.
            if content_length > 65536:
                raise _RequestError(
                    http.HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    'Content-Length exceeds limit: %d' % content_length,
                )
            await self._request_buffer.read_into(request_body, content_length)
        request_body.close()
        environ['wsgi.input'] = request_body

        return environ

    # RFC 7230 token.
    _TOKEN = r'[a-zA-Z0-9!#$%&\'*+\-.^_`|~]+'

    # RFC 7230 request-target is quite complex; for now we just use
    # `[^\s]+` to match it.
    _REQUEST_LINE_PATTERN = re.compile(
        r'(%s) ([^\s]+) (HTTP/\d\.\d)\r\n' % _TOKEN,
        re.ASCII,
    )

    def _parse_request_line(self, line, environ):
        match = self._REQUEST_LINE_PATTERN.fullmatch(line)
        if not match:
            raise _RequestError(
                http.HTTPStatus.BAD_REQUEST,
                'invalid request line: %r' % line,
            )
        method, path, http_version = match.groups()
        if http_version != 'HTTP/1.1':
            LOG.debug('request is not HTTP/1.1 but %s', http_version)
        environ['REQUEST_METHOD'] = method.upper()
        i = path.find('?')
        if i < 0:
            environ['PATH_INFO'] = path
            environ['QUERY_STRING'] = ''
        else:
            environ['PATH_INFO'] = path[:i]
            environ['QUERY_STRING'] = path[i + 1:]

    # NOTE: RFC 7230 specifies obsolete line folding (to represent
    # multi-line header value) for historic reason, which we do not
    # implement.
    _HEADER_PATTERN = re.compile(
        r'(%s):[ \t]*(.*?)[ \t]*\r\n' % _TOKEN,
        re.ASCII,
    )

    def _parse_request_header(self, line):
        match = self._HEADER_PATTERN.fullmatch(line)
        if not match:
            raise _RequestError(
                http.HTTPStatus.BAD_REQUEST,
                'invalid request header: %r' % line,
            )
        name, value = match.groups()
        name = name.upper().replace('-', '_')
        if name not in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            name = 'HTTP_' + name
        return name, value


class _RequestBuffer:

    def __init__(self, sock):
        self._sock = sock
        self._buffer = []
        self._size = 0
        self._ended = False

    async def readline_decoded(self, limit=65536):
        line = await self._readline(limit=limit)
        try:
            return line.decode('iso-8859-1')
        except UnicodeDecodeError:
            raise _RequestError(
                http.HTTPStatus.BAD_REQUEST,
                'incorrectly encoded request line: %r' % line,
            ) from None

    async def _readline(self, limit=65536):
        """Read one line from the socket.

        It errs out when line length exceeds the limit.
        """
        if self._buffer:
            ASSERT.equal(len(self._buffer), 1)
            line = self._search_line(0)
            if line is not None:
                return line
        while not self._ended and self._size <= limit:
            data = await self._sock.recv(limit + 1)
            if not data:
                self._ended = True
                break
            self._buffer.append(data)
            self._size += len(data)
            line = self._search_line(-1)
            if line is not None:
                ASSERT.in_(len(self._buffer), (0, 1))
                return line
        if self._size > limit:
            raise _TooLong('request line length exceeds %d' % limit)
        if self._buffer:
            remaining = b''.join(self._buffer)
            self._buffer.clear()
            self._size = 0
            return remaining
        else:
            return b''

    def _search_line(self, i):
        if i < 0:
            i += len(self._buffer)
        j = self._buffer[i].find(b'\n')
        if j < 0:
            return None
        j += 1
        if i == 0:
            if j == len(self._buffer[0]):
                line = self._buffer.pop(0)
            else:
                line = self._buffer[0][:j]
                self._buffer[0] = self._buffer[0][j:]
        else:
            if j == len(self._buffer[i]):
                parts = self._buffer[:i + 1]
                del self._buffer[:i + 1]
            else:
                parts = self._buffer[:i]
                parts.append(self._buffer[i][:j])
                self._buffer[i] = self._buffer[i][j:]
                del self._buffer[:i]
            line = b''.join(parts)
        self._size -= len(line)
        return line

    async def read_into(self, stream, size):
        while size > 0:
            if self._buffer:
                if size < len(self._buffer[0]):
                    data = self._buffer[0][:size]
                    self._buffer[0] = self._buffer[0][size:]
                else:
                    data = self._buffer.pop(0)
                self._size -= len(data)
            elif self._ended:
                break
            else:
                data = await self._sock.recv(size)
                if not data:
                    self._ended = True
                    break
            size -= len(data)
            stream.write_nonblocking(data)


@enum.unique
class _SendMechanisms(enum.Enum):
    UNDECIDED = enum.auto()
    SEND = enum.auto()
    SENDFILE = enum.auto()


class _ApplicationContext:

    def __init__(self):
        self._is_committed = False
        self._status = None
        self._headers = []
        self._send_mechanism = _SendMechanisms.UNDECIDED
        # Set capacity to 1 to prevent excessive buffering.
        self._chunks = queues.Queue(capacity=1)
        self.file = None

    def start_response(self, status, response_headers, exc_info=None):
        if exc_info:
            try:
                if self._is_committed:
                    exc = exc_info[1]
                    if exc is None:
                        exc = exc_info[0]()
                    if exc.__traceback__ is not exc_info[2]:
                        exc.with_traceback(exc_info[2])
                    raise exc
            finally:
                exc_info = None  # Avoid dangling cyclic ref.
        else:
            ASSERT.false(self._is_committed)

        # Get the status code from status line like "200 OK".
        self._status = http.HTTPStatus(int(status.split(maxsplit=1)[0]))
        self._headers = [
            (name.encode('iso-8859-1'), value.encode('iso-8859-1'))
            for name, value in response_headers
        ]

        return self.write

    def commit(self):
        """Commit the status and headers.

        This effectively "locks" the context from further changing
        status or headers via `start_response`.
        """
        self._is_committed = True

    @property
    def status(self):
        # It is unsafe to read status before the context is committed.
        ASSERT.true(self._is_committed)
        return ASSERT.not_none(self._status)

    @property
    def headers(self):
        # It is unsafe to read headers before the context is committed.
        ASSERT.true(self._is_committed)
        return self._headers

    async def get_body_chunk(self):
        try:
            return await self._chunks.get()
        except queues.Closed:
            return b''

    async def put_body_chunk(self, chunk):
        ASSERT.is_not(self._send_mechanism, _SendMechanisms.SENDFILE)
        self._send_mechanism = _SendMechanisms.SEND
        if chunk:
            await self._chunks.put(chunk)

    # According to WSGI spec, `write` is only intended for maintaining
    # backward compatibility.
    async def write(self, data):
        await self.put_body_chunk(data)
        return len(data)

    def end_body_chunks(self):
        self._chunks.close()

    def sendfile(self, file):
        # sendfile can be called only once.
        ASSERT.is_(self._send_mechanism, _SendMechanisms.UNDECIDED)
        ASSERT.not_none(file)
        self._send_mechanism = _SendMechanisms.SENDFILE
        self.file = file


class _ResponseQueue:

    # These timeouts are for preventing a client who refuses to receive
    # data blocking send/sendfile forever.
    #
    # TODO: Make these configurable.
    _SEND_TIMEOUT = 2
    _SENDFILE_TIMEOUT = 8

    _ENCODED_REASONS = {
        status: status.phrase.encode('iso-8859-1')
        for status in http.HTTPStatus
    }

    def __init__(self, sock):
        self._sock = sock
        self._has_begun = False
        self._headers_sent = locks.Event()
        self._send_mechanism = _SendMechanisms.UNDECIDED

    async def begin(self, status, headers):
        ASSERT.false(self._has_begun)
        self._has_begun = True

        buffer = io.BytesIO()
        buffer.write(
            b'HTTP/1.1 %d %s\r\n' % (status, self._ENCODED_REASONS[status])
        )
        for key, value in headers:
            buffer.write(b'%s: %s\r\n' % (key, value))
        buffer.write(b'\r\n')

        await self._send_all(buffer.getvalue())
        self._headers_sent.set()

    def has_begun(self):
        return self._has_begun

    async def put_body_chunk(self, chunk):
        ASSERT.true(self._has_begun)
        ASSERT.is_not(self._send_mechanism, _SendMechanisms.SENDFILE)
        self._send_mechanism = _SendMechanisms.SEND
        await self._headers_sent.wait()
        if chunk:
            await self._send_all(chunk)

    async def sendfile(self, file):
        ASSERT.true(self._has_begun)
        # sendfile can be called only once.
        ASSERT.is_(self._send_mechanism, _SendMechanisms.UNDECIDED)
        ASSERT.not_none(file)
        self._send_mechanism = _SendMechanisms.SENDFILE
        await self._headers_sent.wait()
        with timers.timeout_after(self._SENDFILE_TIMEOUT):
            return await self._sock.sendfile(file)

    def end(self):
        ASSERT.true(self._has_begun)
        ASSERT.true(self._headers_sent.is_set())
        self._has_begun = False
        self._headers_sent.clear()
        self._send_mechanism = _SendMechanisms.UNDECIDED

    async def _send_all(self, data):
        data = memoryview(data)
        num_sent = 0
        while num_sent < len(data):
            with timers.timeout_after(self._SEND_TIMEOUT):
                num_sent += await self._sock.send(data[num_sent:])
