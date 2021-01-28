"""Asynchronous WSGI Server/Gateway implementation."""

__all__ = [
    'HttpSession',
]

import collections
import http
import io
import logging
import re
import socket

from g1.asyncs.bases import streams
from g1.asyncs.bases import timers
from g1.bases.assertions import ASSERT

LOG = logging.getLogger(__name__)


# Should we expose this class?
class _HttpError(Exception):

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class HttpSession:

    _MAX_NUM_HEADERS = 128

    # TODO: Make these configurable.
    _KEEP_ALIVE_IDLE_TIMEOUT = 8
    # A session may stay longer even when the number of requests exceeds
    # this number if the WSGI application explicitly set Keep-Alive in
    # response headers.
    _MAX_NUM_REQUESTS_PER_SESSION = 1024

    _REQUEST_LINE_PATTERN = re.compile(
        r'\s*([^\s]+)\s+([^\s]+)\s+([^\s]+)\s*\r?\n',
        re.IGNORECASE,
    )

    _HEADER_PATTERN = re.compile(r'\s*([^\s]+)\s*:\s*(.*[^\s])\s*\r?\n')
    _HEADER_NAME_PATTERN = re.compile(r'[a-zA-Z0-9_-]+')

    _ENCODED_REASONS = {
        status: status.phrase.encode('iso-8859-1')
        for status in http.HTTPStatus
    }

    def __init__(self, sock, application, base_environ):
        self._sock = sock
        self._application = application
        self._base_environ = base_environ
        self._request_buffer = _RequestBuffer(self._sock)
        self._response_buffer = io.BytesIO()
        self._send_keep_alive = True

    async def __call__(self):
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with self._sock:
            try:
                num_requests = 0
                while True:
                    keep_alive_sent = await self._handle_one()
                    await self._flush()
                    if not keep_alive_sent:
                        break
                    num_requests += 1
                    if num_requests >= self._MAX_NUM_REQUESTS_PER_SESSION - 1:
                        self._send_keep_alive = False
            except socket.timeout as exc:
                LOG.debug('request timeout: %r', exc)
            except ConnectionResetError:
                LOG.debug('connection reset by client')
            except BrokenPipeError:
                LOG.debug('connection closed by client')

    async def _handle_one(self):
        """Handle one request.

        It returns true if a "Keep-Alive" is sent to the client.
        """
        # WSGI requires that the environ argument must be a built-in
        # Python dictionary.
        environ = dict(self._base_environ)

        try:
            with timers.timeout_after(self._KEEP_ALIVE_IDLE_TIMEOUT):
                if not await self._parse_request(environ):
                    return False
        except _HttpError as exc:
            LOG.debug('invalid request: %s %s', exc.status, exc)
            self._send_error(exc.status)
            return False
        except timers.Timeout:
            LOG.debug('keep-alive idle timeout')
            return False

        # Check if client disables Keep-Alive explicitly.
        connection = environ.get('HTTP_CONNECTION')
        if connection is not None and 'keep-alive' not in connection.lower():
            self._send_keep_alive = False

        if environ.get('HTTP_EXPECT', '').lower() == '100-continue':
            self._write_status(http.HTTPStatus.CONTINUE)
            if self._send_keep_alive:
                self._write_keep_alive_header()
            else:
                self._write_not_keep_alive_header()
            self._end_headers()
            return self._send_keep_alive

        response = _Response()
        try:
            await self._run_application(environ, response)
        except Exception:
            LOG.exception('wsgi application error: %r', exc)
            self._send_error(http.HTTPStatus.INTERNAL_SERVER_ERROR)
            return False
        if response.status is None:
            LOG.error('wsgi application did not set status code')
            self._send_error(http.HTTPStatus.INTERNAL_SERVER_ERROR)
            return False

        return self._send_response(response, environ)

    async def _run_application(self, environ, response):
        application = await self._application(environ, response.start_response)
        try:
            if hasattr(application, '__aiter__'):
                async for data in application:
                    response.write(data)
            else:
                for data in application:
                    response.write(data)
        finally:
            if hasattr(application, 'close'):
                await application.close()

    async def _parse_request(self, environ):
        line = await self._request_buffer.readline_decoded()
        if not line:
            return False
        self._parse_request_line(line, environ)

        headers = collections.defaultdict(list)
        while True:
            line = await self._request_buffer.readline_decoded()
            if line in ('', '\n', '\r\n'):
                break
            if len(headers) == self._MAX_NUM_HEADERS:
                raise _HttpError(
                    http.HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE,
                    'number of request headers exceeds %d' %
                    self._MAX_NUM_HEADERS,
                )
            name, value = self._parse_request_header(line)
            if name is not None:
                headers[name].append(value)
        for name, values in headers.items():
            environ[name] = ','.join(values)

        content_length = environ.get('CONTENT_LENGTH')
        if content_length is not None:
            try:
                content_length = int(content_length, base=10)
            except ValueError:
                raise _HttpError(
                    http.HTTPStatus.BAD_REQUEST,
                    'invalid request Content-Length: %r' % content_length,
                ) from None

        request_body = streams.BytesStream()
        if content_length is not None:
            # TODO: Set the limit to 64K for now, but we should rewrite
            # this to NOT load the entire request body into the memory.
            if content_length > 65536:
                raise _HttpError(
                    http.HTTPStatus.BAD_REQUEST,
                    'Content-Length exceeds limit: %d' % content_length,
                )
            await self._request_buffer.read_into(request_body, content_length)
        request_body.close()
        environ['wsgi.input'] = request_body

        return True

    def _parse_request_line(self, line, environ):
        match = self._REQUEST_LINE_PATTERN.fullmatch(line)
        if not match:
            raise _HttpError(
                http.HTTPStatus.BAD_REQUEST,
                'invalid request line: %r' % line,
            )
        method, path, http_version = match.groups()
        if http_version.upper() != 'HTTP/1.1':
            LOG.debug('request is not HTTP/1.1 but %s', http_version)
        environ['REQUEST_METHOD'] = method.upper()
        i = path.find('?')
        if i < 0:
            environ['PATH_INFO'] = path
            environ['QUERY_STRING'] = ''
        else:
            environ['PATH_INFO'] = path[:i]
            environ['QUERY_STRING'] = path[i + 1:]

    def _parse_request_header(self, line):
        match = self._HEADER_PATTERN.fullmatch(line)
        if not match:
            raise _HttpError(
                http.HTTPStatus.BAD_REQUEST,
                'invalid request header: %r' % line,
            )
        name, value = match.groups()
        if not self._HEADER_NAME_PATTERN.fullmatch(name):
            LOG.debug('ignore malformed request header: %r', line)
            return None, None
        name = name.upper().replace('-', '_')
        if name not in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            name = 'HTTP_' + name
        return name, value

    def _send_response(self, response, environ):
        self._write_status(response.status)

        has_connection = False
        keep_alive_sent = False
        content_length = None
        for key, value in response.headers:
            if key.lower() == b'connection':
                has_connection = True
                keep_alive_sent = b'keep-alive' in value.lower()
            if key.lower() == b'content-length':
                content_length = value
            self._write_header(key, value)

        if not has_connection:
            if self._send_keep_alive:
                self._write_keep_alive_header()
                keep_alive_sent = True
            else:
                self._write_not_keep_alive_header()

        # Response body is omitted for cases described in:
        # * RFC7230: 3.3. 1xx, 204 No Content, 304 Not Modified.
        # * RFC7231: 6.3.6. 205 Reset Content.
        omit_body = 100 <= response.status < 200 or response.status in (
            http.HTTPStatus.NO_CONTENT,
            http.HTTPStatus.RESET_CONTENT,
            http.HTTPStatus.NOT_MODIFIED,
        )
        if omit_body:
            body = None
        else:
            body = response.get_body()
            size = b'%d' % len(body)
            if content_length is None:
                self._write_header(b'Content-Length', size)
            elif content_length != size:
                LOG.warning(
                    'expect Content-Length %r, not %r', size, content_length
                )

        self._end_headers()

        if not omit_body and environ.get('REQUEST_METHOD') != 'HEAD':
            self._response_buffer.write(body)

        return keep_alive_sent

    def _send_error(self, status):
        self._write_status(status)
        self._write_not_keep_alive_header()
        self._end_headers()

    def _write_status(self, status):
        self._response_buffer.write(
            b'HTTP/1.1 %d %s\r\n' % (status, self._ENCODED_REASONS[status])
        )

    def _write_keep_alive_header(self):
        self._write_header(b'Connection', b'keep-alive')

    def _write_not_keep_alive_header(self):
        self._write_header(b'Connection', b'close')

    def _write_header(self, key, value):
        self._response_buffer.write(b'%s: %s\r\n' % (key, value))

    def _end_headers(self):
        self._response_buffer.write(b'\r\n')

    async def _flush(self):
        response = self._response_buffer.getvalue()
        self._response_buffer = io.BytesIO()
        num_sent = 0
        while num_sent < len(response):
            num_sent += await self._sock.send(response[num_sent:])


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
            raise _HttpError(
                http.HTTPStatus.BAD_REQUEST,
                'incorrectly encoded request line: %r' % line,
            )

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
            raise _HttpError(
                http.HTTPStatus.REQUEST_URI_TOO_LONG,
                'request line length exceeds %d' % limit,
            )
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


class _Response:

    def __init__(self):
        self.status = None
        self.headers = []
        self._body_buffer = io.BytesIO()

    def start_response(self, status, response_headers, exc_info=None):
        if exc_info:
            exc_info = None  # Avoid dangling cyclic ref.
            # Clear response body on error.  Or should we also clear it
            # on non-error path?
            self._body_buffer = io.BytesIO()

        # Get the status code from status line like "200 OK".
        self.status = http.HTTPStatus(int(status.split(maxsplit=1)[0]))
        self.headers = [
            (name.encode('iso-8859-1'), value.encode('iso-8859-1'))
            for name, value in response_headers
        ]

        return self.write

    # According to WSGI spec, write is only intended for maintaining
    # backward compatibility; so let's declare it as not async for the
    # ease of use.
    def write(self, data):
        self._body_buffer.write(data)

    def get_body(self):
        return self._body_buffer.getvalue()
