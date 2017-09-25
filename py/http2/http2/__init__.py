__all__ = [
    'Session',
    'SessionError',
    'Stream',
    'StreamClosed',
    # HTTP/2 entities
    'Request',
    'Response',
    # HTTP/2 entity properties
    'Method',
    'Scheme',
    'Status',
    # Helpers
    'get_library_version',
    'make_ssl_context',
]

from http import HTTPStatus as Status  # Rename for consistency
import ctypes
import enum
import functools
import io
import logging

from curio import socket
from curio import ssl
import curio

from garage import asserts
from garage.asyncs import queues

from .nghttp2 import *


LOG = logging.getLogger(__name__)


py_object_p = ctypes.POINTER(ctypes.py_object)


def get_library_version():
    version = nghttp2_version(0).contents
    return {
        'age': version.age,
        'version_num': version.version_num,
        'version_str': version.version_str.decode('utf-8'),
        'proto_str': version.proto_str.decode('utf-8'),
    }


def make_ssl_context(certfile, keyfile, *, client_authentication=False):
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certfile, keyfile)
    if client_authentication:
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.load_verify_locations(cafile=certfile)
    if ssl.HAS_ALPN:
        ssl_context.set_alpn_protocols([NGHTTP2_PROTO_VERSION_ID])
    if ssl.HAS_NPN:
        ssl_context.set_npn_protocols([NGHTTP2_PROTO_VERSION_ID])
    return ssl_context


class SessionError(Exception):
    pass


class StreamClosed(SessionError):
    pass


class Method(enum.Enum):
    OPTIONS = b'OPTIONS'
    GET = b'GET'
    HEAD = b'HEAD'
    POST = b'POST'
    PUT = b'PUT'
    DELETE = b'DELETE'
    TRACE = b'TRACE'
    CONNECT = b'CONNECT'


class Scheme(enum.Enum):
    HTTP = b'http'
    HTTPS = b'https'


class Session:
    """Represent an HTTP/2 session to the server.

    You spawn a serve() task which will process the HTTP/2 traffic, and
    you interact with the serve() task via the public interface of the
    Session object.
    """

    INCOMING_BUFFER_SIZE = 65536  # TCP packet <= 64KB

    MAX_CONCURRENT_STREAMS = 128

    SETTINGS_TIMEOUT = 5  # Unit: seconds

    def __init__(self, sock):

        self._sock = sock

        # Guard self._sendall()
        self._lock = curio.Lock()

        self._session = None  # Own nghttp2_session object
        self._user_data = None  # Own `py_object(self)`
        self._streams = {}  # Own Stream objects
        self._stream_queue = queues.Queue()

        # Set to non-None to start settings timer
        self._settings_timeout = None

        # Track the current callback for better logging
        self._current_callback = None

        # For PushPromise
        self._scheme = self._guess_scheme(self._sock)
        self._host = self._sock.getsockname()[0].encode('ascii')

    @property
    def _id(self):
        if self._session is not None:
            return hex(ctypes.addressof(self._session.contents))
        else:
            return None

    @staticmethod
    def _guess_scheme(sock):
        try:
            sock.context
        except AttributeError:
            return Scheme.HTTP
        else:
            return Scheme.HTTPS

    def _log(self, logger, message, *args):
        logger('session=%s: %s: ' + message,
               self._id, self._current_callback or '?', *args)

    _debug = functools.partialmethod(_log, LOG.debug)
    _info = functools.partialmethod(_log, LOG.info)
    _warning = functools.partialmethod(_log, LOG.warning)

    async def serve(self):
        if self._session is not None:
            raise SessionError('session is already active: %s' % self._id)

        # Create nghttp2_session object
        self._session, self._user_data = self._make_session()
        LOG.info('session=%s: create %s session for client: %s',
                 self._id, self._scheme.name, self._sock.getpeername())

        try:
            # Disable Nagle algorithm
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            # Set SETTINGS frame
            settings = (nghttp2_settings_entry * 2)()
            settings[0].settings_id = NGHTTP2_SETTINGS_MAX_CONCURRENT_STREAMS
            settings[0].value = self.MAX_CONCURRENT_STREAMS
            settings[1].settings_id = NGHTTP2_SETTINGS_INITIAL_WINDOW_SIZE
            settings[1].value = NGHTTP2_INITIAL_WINDOW_SIZE
            nghttp2_submit_settings(
                self._session, NGHTTP2_FLAG_NONE, settings, len(settings))

            # Start serving!
            error_code = NGHTTP2_NO_ERROR
            try:
                while True:
                    async with curio.timeout_after(self._settings_timeout):
                        if not await self._serve_tick():
                            break
            except curio.TaskTimeout:
                LOG.warning('session=%s: settings timeout', self._id)
                error_code = NGHTTP2_SETTINGS_TIMEOUT

            # Graceful exit
            for stream in self._streams.values():
                stream._on_close(NGHTTP2_NO_ERROR)
            nghttp2_session_terminate_session(self._session, error_code)
            await self._sendall()

        finally:
            LOG.info('session=%s: destroy session', self._id)
            nghttp2_session_del(self._session)

            # Disown objects
            self._session = None
            self._user_data = None
            self._streams.clear()
            self._stream_queue.close()

            await self._sock.close()

    async def _serve_tick(self):
        try:
            data = await self._sock.recv(self.INCOMING_BUFFER_SIZE)
        except OSError as exc:
            LOG.warning('session=%s: %r', self._id, exc)
            return False

        LOG.debug('session=%s: recv %d bytes', self._id, len(data))
        if not data:
            LOG.info('session=%s: connection is closed', self._id)
            return False

        try:
            rc = nghttp2_session_mem_recv(self._session, data, len(data))
        except Nghttp2Error as exc:
            if exc.error_code == NGHTTP2_ERR_BAD_CLIENT_MAGIC:
                LOG.warning('session=%s: bad client magic', self._id)
                return False
            raise

        if rc != len(data):
            # In the current implementation, nghttp2_session_mem_recv
            # always tries to processes all input data normally.
            raise SessionError(
                'expect nghttp2_session_mem_recv to process %d bytes but only %d' %
                (len(data), rc))

        if not await self._sendall():
            LOG.debug('session=%s: bye!', self._id)
            return False

        return True

    def _make_session(self):
        session = ctypes.POINTER(nghttp2_session)()

        # You should own user_data to prevent it from being garbage
        # collected
        user_data = ctypes.py_object(self)

        callbacks = ctypes.POINTER(nghttp2_session_callbacks)()
        nghttp2_session_callbacks_new(ctypes.byref(callbacks))

        try:
            nghttp2_session_callbacks_set_on_frame_recv_callback(
                callbacks, self._on_frame_recv)
            nghttp2_session_callbacks_set_on_data_chunk_recv_callback(
                callbacks, self._on_data_chunk_recv)
            nghttp2_session_callbacks_set_on_frame_send_callback(
                callbacks, self._on_frame_send)
            nghttp2_session_callbacks_set_on_frame_not_send_callback(
                callbacks, self._on_frame_not_send)
            nghttp2_session_callbacks_set_on_stream_close_callback(
                callbacks, self._on_stream_close)
            nghttp2_session_callbacks_set_on_begin_headers_callback(
                callbacks, self._on_begin_headers)
            nghttp2_session_callbacks_set_on_header_callback(
                callbacks, self._on_header)

            nghttp2_session_server_new(
                ctypes.byref(session),
                callbacks,
                _addrof(user_data),
            )

            return session, user_data

        finally:
            nghttp2_session_callbacks_del(callbacks)

    async def _sendall(self):
        async with self._lock:
            return await self._sendall_impl()

    async def _sendall_impl(self):
        asserts.not_none(self._session)

        buffers = []
        total_length = 0
        while True:
            buffer = ctypes.c_void_p()
            length = nghttp2_session_mem_send(
                self._session, ctypes.byref(buffer))
            if length == 0:
                break
            buffers.append(ctypes.string_at(buffer, length))
            total_length += length

        LOG.debug('session=%s: send %d bytes from %d parts',
                  self._id, total_length, len(buffers))
        # Unfortunately SSLSocket disallow scatter/gather sendmsg.
        try:
            await self._sock.sendall(b''.join(buffers))
        except OSError as exc:
            LOG.warning('session=%s: %r', self._id, exc)
            return False

        return (nghttp2_session_want_read(self._session) != 0 or
                nghttp2_session_want_write(self._session) != 0)

    class _CallbackReturn(Exception):
        def __init__(self, code):
            super().__init__()
            self.code = code

    def declare_callback(c_func_signature):
        def wrap(py_func):
            def trampoline(session, *args):
                try:
                    self = ctypes.cast(args[-1], py_object_p).contents.value
                    # Callbacks should not be nested
                    asserts.none(self._current_callback)
                    self._current_callback = py_func.__name__
                    try:
                        return py_func(self, session, *args[:-1])
                    finally:
                        self._current_callback = None
                except Session._CallbackReturn as ret:
                    return ret.code
                except Exception:
                    LOG.exception('session=0x%x: err when calling %s',
                                  ctypes.addressof(session.contents),
                                  py_func.__name__)
                    return NGHTTP2_ERR_CALLBACK_FAILURE
            return c_func_signature(trampoline)
        return wrap

    @declare_callback(nghttp2_on_frame_recv_callback)
    def _on_frame_recv(self, session, frame):
        frame = frame.contents
        self._debug('type=%d, stream=%d', frame.hd.type, frame.hd.stream_id)
        if (frame.hd.type == NGHTTP2_SETTINGS and
                (frame.hd.flags & NGHTTP2_FLAG_ACK) != 0):
            self._debug('clear settings timeout')
            self._settings_timeout = None
        if (frame.hd.type == NGHTTP2_HEADERS and
                frame.headers.cat == NGHTTP2_HCAT_REQUEST and
                (frame.hd.flags & NGHTTP2_FLAG_END_STREAM) != 0):
            stream = self._get_stream(frame.hd.stream_id)
            stream._on_request_done()
            self._stream_queue.put_nowait(stream)
        if (frame.hd.type == NGHTTP2_DATA and
                (frame.hd.flags & NGHTTP2_FLAG_END_STREAM) != 0):
            stream = self._get_stream(frame.hd.stream_id)
            stream._on_request_done()
            self._stream_queue.put_nowait(stream)
        return 0

    @declare_callback(nghttp2_on_data_chunk_recv_callback)
    def _on_data_chunk_recv(self, session, flags, stream_id, data, length):
        self._debug('stream=%d, length=%d', stream_id, length)
        self._get_stream(stream_id)._on_data(ctypes.string_at(data, length))
        return 0

    @declare_callback(nghttp2_on_frame_send_callback)
    def _on_frame_send(self, session, frame):
        frame = frame.contents
        self._debug('type=%d, stream=%d', frame.hd.type, frame.hd.stream_id)
        if frame.hd.type == NGHTTP2_SETTINGS:
            if (frame.hd.flags & NGHTTP2_FLAG_ACK) != 0:
                return 0
            self._debug('set settings timeout: %f', self.SETTINGS_TIMEOUT)
            self._settings_timeout = self.SETTINGS_TIMEOUT
        if (frame.hd.type == NGHTTP2_HEADERS and
                (frame.hd.flags & NGHTTP2_FLAG_END_STREAM) != 0):
            return self._rst_stream_if_not_closed(frame.hd.stream_id)
        if frame.hd.type == NGHTTP2_PUSH_PROMISE:
            # For PUSH_PROMISE, send push response immediately
            stream = self._get_stream(frame.push_promise.promised_stream_id)
            stream._submit_response_nowait(stream.response)
        return 0

    @declare_callback(nghttp2_on_frame_not_send_callback)
    def _on_frame_not_send(self, session, frame, error_code):
        frame = frame.contents
        self._debug('type=%d, stream=%d, error_code=%d',
                    frame.hd.type, frame.hd.stream_id, error_code)
        if frame.hd.type == NGHTTP2_PUSH_PROMISE:
            # We have to remove stream here; otherwise, it is not
            # removed until session is terminated
            self._warning('remove stream %d', frame.hd.stream_id)
            self._get_stream(frame.hd.stream_id, remove=True)
        return 0

    @declare_callback(nghttp2_on_stream_close_callback)
    def _on_stream_close(self, session, stream_id, error_code):
        self._debug('stream=%d, error_code=%d', stream_id, error_code)
        self._get_stream(stream_id, remove=True)._on_close(error_code)
        return 0

    @declare_callback(nghttp2_on_begin_headers_callback)
    def _on_begin_headers(self, session, frame):
        frame = frame.contents
        self._debug('type=%d, stream=%d', frame.hd.type, frame.hd.stream_id)
        if (frame.hd.type == NGHTTP2_HEADERS and
                frame.headers.cat == NGHTTP2_HCAT_REQUEST):
            self._make_stream(frame.hd.stream_id)
        return 0

    @declare_callback(nghttp2_on_header_callback)
    def _on_header(
            self, session, frame, name, namelen, value, valuelen, flags):
        frame = frame.contents
        name = ctypes.string_at(name, namelen)
        values = ctypes.string_at(value, valuelen).split(b'\x00')
        self._debug('type=%d, stream=%d, %r=%r',
                    frame.hd.type, frame.hd.stream_id, name, values)
        self._get_stream(frame.hd.stream_id)._on_header(name, values)
        return 0

    @declare_callback(nghttp2_data_source_read_callback)
    def _on_data_source_read(
            self, session, stream_id, buf, length, data_flags, source):
        self._debug('stream=%d', stream_id)
        source = source.contents
        read = ctypes.cast(source.ptr, py_object_p).contents.value
        data, error_code = read(length)
        if error_code != 0:
            return error_code
        num_read = len(data)
        if num_read:
            ctypes.memmove(buf, data, num_read)
        if num_read == 0:
            data_flags[0] = NGHTTP2_DATA_FLAG_EOF
            self._rst_stream_if_not_closed(stream_id)
        return num_read

    del declare_callback

    def _make_stream(self, stream_id):
        if stream_id in self._streams:
            self._warning('stream=%d: stream object exist', stream_id)
            raise Session._CallbackReturn(0)
        stream = Stream(self, stream_id)
        self._streams[stream_id] = stream
        return stream

    def _get_stream(self, stream_id, *, remove=False):
        try:
            if remove:
                return self._streams.pop(stream_id)
            else:
                return self._streams[stream_id]
        except KeyError:
            self._warning('stream=%d: no stream object', stream_id)
            raise Session._CallbackReturn(0) from None

    def _rst_stream(self, stream_id, error_code=NGHTTP2_INTERNAL_ERROR):
        self._debug('stream=%d: rst_stream due to %d', stream_id, error_code)
        return nghttp2_submit_rst_stream(
            self._session, NGHTTP2_FLAG_NONE, stream_id, error_code)

    def _rst_stream_if_not_closed(self, stream_id):
        rc = nghttp2_session_get_stream_remote_close(self._session, stream_id)
        if rc == 0:
            return self._rst_stream(stream_id, NGHTTP2_NO_ERROR)
        return 0

    async def next_stream(self):
        """Return next stream or None when the session is closed."""
        try:
            return await self._stream_queue.get()
        except queues.Closed:
            return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self._stream_queue.get()
        except queues.Closed:
            raise StopAsyncIteration from None


class Stream:
    """Represent HTTP/2 stream."""

    def __init__(self, session, stream_id):

        # Store a copy of session ID so that we may print stream even
        # after the session is clsoed.
        self._session_id = session._id
        self._id = stream_id

        self._session = session  # Cyclic reference :(

        self.request = None
        self._headers = []
        self._data_chunks = []

        self.response = None  # Own response

    def __str__(self):
        return '<Stream session=%s stream=%d>' % (self._session_id, self._id)

    # For these callbacks (the `_on_X` methods), Session should not call
    # them after the stream is closed; otherwise it is a bug, and thus
    # we raise AssertionError.

    def _on_header(self, name, values):
        asserts.not_none(self._session)
        asserts.none(self.request)
        for value in values:
            self._headers.append((name, value))

    def _on_data(self, data):
        asserts.not_none(self._session)
        asserts.none(self.request)
        self._data_chunks.append(data)

    def _on_request_done(self):
        asserts.not_none(self._session)
        asserts.none(self.request)
        if self._data_chunks:
            body = b''.join(self._data_chunks)
        else:
            body = None
        self.request = Request._make(self._headers, body)
        del self._headers
        del self._data_chunks

    def _on_close(self, error_code):
        asserts.not_none(self._session)
        LOG.debug('%s: close due to %d', self, error_code)
        self._session = None  # Break cycle

    # For the submit_X methods below, it is possible that that are
    # called after the stream is closed; thus we throw StreamClosed.

    def _ensure_not_closed(self):
        if self._session is None:
            raise StreamClosed

    # Non-blocking version of submit() that should be called in the
    # Session object's callback functions.
    def _submit_response_nowait(self, response):
        self._ensure_not_closed()
        asserts.in_(self.response, (None, response))
        LOG.debug('%s: submit response', self)
        owners = []
        nva, nvlen = response._make_headers(self._session, owners)
        try:
            nghttp2_submit_response(
                self._session._session,
                self._id,
                nva, nvlen,
                response._make_data_provider_ptr(),
            )
        except Nghttp2Error:
            self._session._rst_stream(self._id)
            raise
        self.response = response

    async def submit_response(self, response):
        """Send response to client."""
        self._submit_response_nowait(response)
        await self._session._sendall()

    async def submit_push_promise(self, request, response):
        """Push resource to client.

        Note that this must be used before submit().
        """
        self._ensure_not_closed()
        LOG.debug('%s: submit push promise', self)

        owners = []
        nva, nvlen = request._make_headers(self._session, owners)

        promised_stream_id = nghttp2_submit_push_promise(
            self._session._session,
            NGHTTP2_FLAG_NONE,
            self._id,
            nva, nvlen,
            None,
        )
        LOG.debug('%s: push promise stream: %d', self, promised_stream_id)

        promised_stream = self._session._make_stream(promised_stream_id)
        promised_stream.response = response

        await self._session._sendall()

    async def submit_rst_stream(self, error_code=NGHTTP2_INTERNAL_ERROR):
        self._ensure_not_closed()
        self._session._rst_stream(self._id, error_code)
        await self._session._sendall()

    class Buffer:
        """Response body buffer."""

        def __init__(self, stream):
            self._stream = stream  # Cyclic reference :(
            self._data_chunks = []
            self._deferred = False
            self._aborted = False
            self._closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, *_):
            if exc_type:
                await self.abort()
            else:
                await self.close()

        def _read(self, length):
            if self._aborted:
                return b'', NGHTTP2_ERR_TEMPORAL_CALLBACK_FAILURE
            elif not self._data_chunks:
                if self._closed:
                    return b'', 0
                else:
                    self._deferred = True
                    return b'', NGHTTP2_ERR_DEFERRED
            elif length >= len(self._data_chunks[0]):
                return bytes(self._data_chunks.pop(0)), 0
            else:
                data = self._data_chunks[0][:length]
                self._data_chunks[0] = self._data_chunks[0][length:]
                return bytes(data), 0

        async def write(self, data):
            asserts.precond(
                not self._aborted and not self._closed,
                'expect Buffer state: not %r and not %r == True',
                self._aborted, self._closed,
            )
            if data:
                self._data_chunks.append(memoryview(data))
                await self._send()
            return len(data)

        # Note that while Session.serve() will continue sending data to
        # the client after buffer is aborted or closed, we still need to
        # call self._send() in abort() and close() since Session.serve()
        # could be blocked on socket.recv() and make no progress.

        async def abort(self):
            asserts.precond(
                not self._aborted and not self._closed,
                'expect Buffer state: not %r and not %r == True',
                self._aborted, self._closed,
            )
            self._aborted = True
            await self._send()
            self._stream = None  # Break cycle

        async def close(self):
            asserts.precond(
                not self._aborted and not self._closed,
                'expect Buffer state: not %r and not %r == True',
                self._aborted, self._closed,
            )
            self._closed = True
            await self._send()
            self._stream = None  # Break cycle

        async def _send(self):
            if self._stream._session is None:
                return  # This stream was closed
            if self._deferred:
                nghttp2_session_resume_data(
                    self._stream._session._session, self._stream._id)
                self._deferred = False
            await self._stream._session._sendall()

    def make_buffer(self):
        return self.Buffer(self)


class Entity:

    def _make_headers(self, session, owners):
        nvlen = self._get_num_headers()
        nva = (nghttp2_nv * nvlen)()
        for nv, (name, value) in zip(nva, self._iter_headers(session)):
            self._set_nv(nv, name, value, owners)
        return nva, nvlen

    def _get_num_headers(self):
        raise NotImplementedError

    def _iter_headers(self, session):
        raise NotImplementedError

    @staticmethod
    def _set_nv(nv, name, value, owners):
        nv.name = Entity._bytes_to_void_ptr(name, owners)
        nv.namelen = len(name)
        nv.value = Entity._bytes_to_void_ptr(value, owners)
        nv.valuelen = len(value)
        nv.flags = NGHTTP2_NV_FLAG_NONE

    @staticmethod
    def _bytes_to_void_ptr(byte_string, owners):
        buffer = ctypes.create_string_buffer(byte_string, len(byte_string))
        owners.append(buffer)
        return _addrof(buffer)


class Request(Entity):

    @classmethod
    def _make(cls, headers, body):
        kwargs = {}
        extra_headers = []
        for name, value in headers:
            if name == b':method':
                kwargs['method'] = Method(value)
            elif name == b':scheme':
                kwargs['scheme'] = Scheme(value)
            elif name == b':authority':
                kwargs['authority'] = value
            elif name == b':path':
                kwargs['path'] = value
            else:
                extra_headers.append((name, value))
        if len(kwargs) != 4:
            raise ValueError('miss HTTP/2 headers: %r' % headers)
        return cls(headers=extra_headers, body=body, **kwargs)

    def __init__(self, *,
                 method=Method.GET,
                 scheme=None,
                 authority=None,
                 path,
                 headers=None,
                 body=None):
        self.method = method
        self.scheme = scheme
        self.authority = authority
        self.path = path
        self.headers = headers or []
        self.body = body

    def _get_num_headers(self):
        # Extra four for method, scheme, authority, and path
        return 4 + len(self.headers)

    def _iter_headers(self, session):
        asserts.not_none(session._scheme)
        asserts.not_none(session._host)
        yield (b':method', self.method.value)
        yield (b':scheme', (self.scheme or session._scheme).value)
        yield (b':authority', self.authority or session._host)
        yield (b':path', self.path)
        yield from self.headers


class Response(Entity):

    def __init__(self, *, status=Status.OK, headers=None, body=None):
        self.status = status
        self.headers = headers or []
        self.body = body
        self._owners = []

    def _get_num_headers(self):
        # Extra one for status
        return 1 + len(self.headers)

    def _iter_headers(self, _):
        yield (b':status', b'%d' % self.status)
        yield from self.headers

    def _make_data_provider_ptr(self):
        if not self.body:
            return None

        if isinstance(self.body, bytes):
            buffer = io.BytesIO(self.body)
            read = lambda length: (buffer.read(length), 0)
        elif isinstance(self.body, Stream.Buffer):
            read = self.body._read
        else:
            raise TypeError('body is neither bytes nor Buffer: %r' % self.body)

        read = ctypes.py_object(read)
        self._owners.append(read)

        provider = nghttp2_data_provider()
        provider.read_callback = Session._on_data_source_read
        provider.source.ptr = _addrof(read)

        return ctypes.byref(provider)


def _addrof(obj):
    return ctypes.cast(ctypes.byref(obj), ctypes.c_void_p)
