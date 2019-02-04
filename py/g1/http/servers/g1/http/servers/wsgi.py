"""Asynchronous WSGI Server/Gateway implementation.

This implements a asynchronous-variant of WSGI server.  It handles one
incoming HTTP/2 session at a time.

At the moment it does not implements HTTP/2 Push.
"""

# We are being clever and have to disable some linter warnings.
# pylint: disable=undefined-variable
# pylint: disable=unused-wildcard-import

__all__ = [
    'HttpSession',
]

import collections
import ctypes
import functools
import logging
import socket
import ssl
import sys
import urllib.parse
import weakref

from g1.asyncs import kernels
from g1.asyncs import servers
from g1.bases.assertions import ASSERT

from . import nghttp2
from .nghttp2 import *

LOG = logging.getLogger(__name__)

#
# Helper for defining callbacks.
#

CALLBACK_NAMES = []


def define_callback(func):
    CALLBACK_NAMES.append(func.__name__)
    return as_callback(func)


def as_callback(func):
    """Convert a Python function into nghttp2 callback function.

    The convention of nghttp2 callback is that the first argument is a
    pointer to C session struct, and the last argument is a pointer to
    user data.

    We use the user data to pass the ``HttpSession`` object to callback
    functions.
    """

    name = func.__name__

    @functools.wraps(func)
    def trampoline(raw_session, *args):
        try:
            *args, session = args
            session = dereference(session)
        except Exception:
            addr = ctypes.addressof(raw_session.contents)
            LOG.exception('%s: session=%#x: trampoline error', name, addr)
            return NGHTTP2_ERR_CALLBACK_FAILURE
        try:
            return func(session, *args)
        except Exception:
            LOG.exception('%s: %r: callback error', name, session)
            return NGHTTP2_ERR_CALLBACK_FAILURE

    return getattr(nghttp2, 'nghttp2_%s_callback' % name)(trampoline)


#
# ctypes helpers.
#
# They are mainly used to convert to/back between ``HttpSession`` object
# and C void pointer (as user data).
#

py_object_p = ctypes.POINTER(ctypes.py_object)


def address_of(obj):
    """Equivalent to ``(void *)&obj``."""
    return ctypes.cast(ctypes.byref(obj), ctypes.c_void_p)


def dereference(addr):
    """Equivalent to ``*(py_object *)ptr``."""
    return ctypes.cast(addr, py_object_p).contents.value


#
# HTTP/2 session object.
#

INCOMING_BUFFER_SIZE = 65536  # As TCP packet is no bigger than 64KB.

ENCODING = 'iso-8859-1'

MAX_CONCURRENT_STREAMS = 128

SETTINGS_TIMEOUT = 5  # Unit: seconds.


class HttpSession:
    """HTTP/2 session.

    A session is further divided into streams, which are basically a
    request-response pair.
    """

    def __init__(self, sock, address, application, environ):

        self._sock = sock
        self._address = address

        self._queue = kernels.TaskCompletionQueue()

        self._outgoing_event = kernels.Event()

        self._cancel_settings_timer = None

        self._application = application
        self._environ = environ
        self._streams = {}
        # Pass a weak ref to ``HttpStream`` objects to break cycle.
        self._ref = weakref.ref(self)

        # Own C objects to prevent them from being garbage-collected.
        self._user_data = ctypes.py_object(self)
        self._session = ctypes.POINTER(nghttp2_session)()
        nghttp2_session_server_new(
            ctypes.byref(self._session),
            CALLBACKS,
            address_of(self._user_data),
        )

    def __repr__(self):
        return '<%s at %#x: %s, session=%#x, streams=%d>' % (
            self.__class__.__qualname__,
            id(self),
            self._address,
            ctypes.addressof(self._session.contents) if self._session else 0,
            len(self._streams),
        )

    async def serve(self):
        ASSERT.not_none(self._session)
        self._prepare()
        try:
            await servers.supervise_handlers(
                self._queue,
                (
                    self._queue.spawn(self._handle_incoming),
                    self._queue.spawn(self._handle_outgoing),
                ),
            )
        finally:
            await self._cleanup()

    def _prepare(self):

        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        settings = (nghttp2_settings_entry * 2)()
        settings[0].settings_id = NGHTTP2_SETTINGS_MAX_CONCURRENT_STREAMS
        settings[0].value = MAX_CONCURRENT_STREAMS
        settings[1].settings_id = NGHTTP2_SETTINGS_INITIAL_WINDOW_SIZE
        settings[1].value = NGHTTP2_INITIAL_WINDOW_SIZE
        nghttp2_submit_settings(
            self._session, NGHTTP2_FLAG_NONE, settings, len(settings)
        )

    async def _handle_incoming(self):

        error_code = NGHTTP2_INTERNAL_ERROR
        try:

            while nghttp2_session_want_read(self._session):

                data = await self._sock.recv(INCOMING_BUFFER_SIZE)
                LOG.debug('serve: %r: recv %d bytes', self, len(data))
                if not data:
                    break

                # In the current nghttp2 implementation,
                # nghttp2_session_mem_recv always tries to processes all
                # input data on success.
                ASSERT.equal(
                    nghttp2_session_mem_recv(self._session, data, len(data)),
                    len(data),
                )

                # Unblock ``_handle_outgoing``.
                self._outgoing_event.set()

            error_code = NGHTTP2_NO_ERROR

        except kernels.Timeout:
            LOG.warning('serve: %r: settings timeout', self)
            self._cancel_settings_timer = None
            error_code = NGHTTP2_SETTINGS_TIMEOUT

        except OSError as exc:
            LOG.warning('serve: %r: sock.recv error', self, exc_info=exc)

        except Nghttp2Error as exc:
            if exc.error_code == NGHTTP2_ERR_BAD_CLIENT_MAGIC:
                LOG.warning('serve: %r: bad client magic', self, exc_info=exc)
            else:
                raise

        finally:
            # NOTE: I have read the docs but am still not sure where and
            # when should we call ``nghttp2_session_terminate_session``.
            # For now it seems to be fine to make the call here.
            nghttp2_session_terminate_session(self._session, error_code)
            # Unblock ``_handle_outgoing`` as we are leaving.
            self._outgoing_event.set()

    async def _handle_outgoing(self):

        # Sadly SSLSocket disallows scatter/gather sendmsg.
        if isinstance(self._sock.target, ssl.SSLSocket):
            send_all = self._send_all
        else:
            ASSERT.isinstance_(self._sock.target, socket.socket)
            send_all = self._sendmsg_all

        try:
            while (
                nghttp2_session_want_read(self._session)
                or nghttp2_session_want_write(self._session)
            ):

                buffers = []
                total_length = 0
                while True:
                    buffer = ctypes.c_void_p()
                    length = nghttp2_session_mem_send(
                        self._session,
                        ctypes.byref(buffer),
                    )
                    if length == 0:
                        break
                    buffers.append(ctypes.string_at(buffer, length))
                    total_length += length

                if not buffers:
                    self._outgoing_event.clear()
                    await self._outgoing_event.wait()
                    continue

                LOG.debug(
                    'serve: %r: send %d bytes in %d pieces',
                    self,
                    total_length,
                    len(buffers),
                )
                await send_all(buffers)

        except OSError as exc:
            LOG.warning('serve: %r: sock.send error', self, exc_info=exc)

    async def _send_all(self, buffers):
        output = b''.join(buffers)
        num_sent = 0
        while num_sent < len(output):
            num_sent += await self._sock.send(output[num_sent:])

    async def _sendmsg_all(self, buffers):
        while buffers:
            num_sent = await self._sock.sendmsg(buffers)
            while buffers:
                if len(buffers[0]) <= num_sent:
                    num_sent -= len(buffers.pop(0))
                else:
                    buffers[0] = buffers[0][num_sent:]
                    break

    async def _cleanup(self):

        self._cancel_settings_timer = None

        self._streams = None

        nghttp2_session_del(self._session)
        self._session = None
        self._user_data = None

        await self._sock.close()

    def _start_settings_timer(self):
        # This should start a timer on the ``_handle_incoming`` task.
        if not self._cancel_settings_timer:
            LOG.debug('start settings timeout: %r', self)
            self._cancel_settings_timer = \
                kernels.timeout_after(SETTINGS_TIMEOUT)

    def _stop_settings_timer(self):
        if self._cancel_settings_timer:
            LOG.debug('stop settings timeout: %r', self)
            self._cancel_settings_timer()
            self._cancel_settings_timer = None

    def _rst_stream_if_not_closed(self, stream_id):
        if nghttp2_session_get_stream_remote_close(self._session, stream_id):
            return 0
        else:
            return self._rst_stream(stream_id, NGHTTP2_NO_ERROR)

    def _rst_stream(self, stream_id, error_code):
        LOG.debug(
            'rst_stream: %r: stream_id=%d, error_code=%d',
            self,
            stream_id,
            error_code,
        )
        return nghttp2_submit_rst_stream(
            self._session, NGHTTP2_FLAG_NONE, stream_id, error_code
        )

    #
    # Callbacks.
    #

    @define_callback
    def on_frame_recv(self, frame):
        frame = frame.contents
        LOG.debug(
            'on_frame_recv: %r: type=%d, stream_id=%d',
            self,
            frame.hd.type,
            frame.hd.stream_id,
        )

        if frame.hd.type == NGHTTP2_SETTINGS:
            if frame.hd.flags & NGHTTP2_FLAG_ACK:
                self._stop_settings_timer()

        elif frame.hd.type == NGHTTP2_HEADERS:
            if frame.headers.cat == NGHTTP2_HCAT_REQUEST:
                stream = self._streams.get(frame.hd.stream_id)
                if not stream:
                    return 0
                if frame.hd.flags & NGHTTP2_FLAG_END_HEADERS:
                    stream.end_request_headers()
                if frame.hd.flags & NGHTTP2_FLAG_END_STREAM:
                    stream.end_request()

        elif frame.hd.type == NGHTTP2_DATA:
            if frame.hd.flags & NGHTTP2_FLAG_END_STREAM:
                stream = self._streams.get(frame.hd.stream_id)
                if not stream:
                    return 0
                stream.end_request()

        return 0

    @define_callback
    def on_begin_headers(self, frame):
        frame = frame.contents
        LOG.debug(
            'on_begin_headers: %r: type=%d, stream_id=%d',
            self,
            frame.hd.type,
            frame.hd.stream_id,
        )

        if frame.hd.type == NGHTTP2_HEADERS:
            if frame.headers.cat == NGHTTP2_HCAT_REQUEST:
                stream_id = ASSERT.not_in(frame.hd.stream_id, self._streams)
                LOG.debug('make stream: %r: stream_id=%d', self, stream_id)
                self._streams[stream_id] = HttpStream(self._ref, stream_id)

        return 0

    @define_callback
    def on_header(self, frame, name, namelen, value, valuelen, flags):
        frame = frame.contents
        name = ctypes.string_at(name, namelen)
        value = ctypes.string_at(value, valuelen)
        LOG.debug(
            'on_header: %r: type=%d, stream_id=%d, flags=%#x, %r=%r',
            self,
            frame.hd.type,
            frame.hd.stream_id,
            flags,
            name,
            value,
        )

        stream = self._streams.get(frame.hd.stream_id)
        if not stream:
            return 0

        stream.set_header(name, value)

        return 0

    @define_callback
    def on_data_chunk_recv(self, flags, stream_id, data, length):
        LOG.debug(
            'on_data_chunk_recv: %r, stream_id=%d, flags=%#x, length=%d',
            self,
            stream_id,
            flags,
            length,
        )

        stream = self._streams.get(stream_id)
        if not stream:
            return 0

        stream.write_request_body(ctypes.string_at(data, length))

        return 0

    @define_callback
    def on_frame_send(self, frame):
        frame = frame.contents
        LOG.debug(
            'on_frame_send: %r: type=%d, stream_id=%d',
            self,
            frame.hd.type,
            frame.hd.stream_id,
        )

        # TODO: Support frame.hd.type == NGHTTP2_PUSH_PROMISE.

        if frame.hd.type == NGHTTP2_SETTINGS:
            if frame.hd.flags & NGHTTP2_FLAG_ACK:
                return 0
            self._start_settings_timer()

        elif frame.hd.type == NGHTTP2_HEADERS:
            if frame.hd.flags & NGHTTP2_FLAG_END_STREAM:
                return self._rst_stream_if_not_closed(frame.hd.stream_id)

        return 0

    @define_callback
    def on_frame_not_send(self, frame, error_code):
        frame = frame.contents
        LOG.debug(
            'on_frame_not_send: %r: type=%d, stream_id=%d, error_code=%d',
            self,
            frame.hd.type,
            frame.hd.stream_id,
            error_code,
        )

        # TODO: Support frame.hd.type == NGHTTP2_PUSH_PROMISE.

        return 0

    @define_callback
    def on_stream_close(self, stream_id, error_code):
        LOG.debug(
            'on_stream_close: %r: stream_id=%d, error_code=%d',
            self,
            stream_id,
            error_code,
        )

        stream = self._streams.pop(stream_id, None)
        if not stream:
            return 0

        stream.close()

        return 0

    #
    # Other callbacks.
    #

    @as_callback
    def data_source_read(self, stream_id, buf, length, data_flags, source):
        LOG.debug(
            'data_source_read: %r, stream_id=%d, length=%d',
            self,
            stream_id,
            length,
        )
        del source  # Unused.

        stream = self._streams[stream_id]

        data = stream.read_response_body(ASSERT.greater(length, 0))
        if data is None:
            return NGHTTP2_ERR_DEFERRED

        if data:
            ctypes.memmove(buf, data, len(data))
        else:
            data_flags[0] = NGHTTP2_DATA_FLAG_EOF
            self._rst_stream_if_not_closed(stream_id)

        return len(data)


CALLBACKS = ctypes.POINTER(nghttp2_session_callbacks)()
nghttp2_session_callbacks_new(ctypes.byref(CALLBACKS))
# pylint: disable=expression-not-assigned
[
    getattr(nghttp2, 'nghttp2_session_callbacks_set_%s_callback' % name)(
        CALLBACKS,
        getattr(HttpSession, name),
    ) for name in CALLBACK_NAMES
]

DATA_PROVIDER = nghttp2_data_provider()
DATA_PROVIDER.read_callback = HttpSession.data_source_read


class HttpStream:
    """HTTP/2 request-response pair.

    This class is closely coupled with ``HttpSession``, and this class
    accesses its private fields (through a weak pointer).
    """

    def __init__(self, session_ref, stream_id):
        self._session_ref = session_ref
        self._stream_id = stream_id
        self._task = None
        self._request_headers = collections.defaultdict(list)
        self._request_body = kernels.BytesStream()
        self._response_headers_sent = False
        self._response_body = kernels.BytesStream()
        self._response_body_deferred = False

    def __repr__(self):
        return '<%s at %#x: session=%r, stream=%d>' % (
            self.__class__.__qualname__,
            id(self),
            self._session_ref(),
            self._stream_id,
        )

    @property
    def _session(self):
        return ASSERT.not_none(self._session_ref())

    #
    # WSGI interface.
    #

    def _get_first_header(self, name):
        return ASSERT.contains(self._request_headers, name)[name][0]

    def _start_wsgi_task(self):
        ASSERT.none(self._task)
        self._task = self._session._queue.spawn(self._run_wsgi)

    async def _run_wsgi(self):

        log_args = (
            self._session._address,
            self._get_first_header(':method'),
            self._get_first_header(':scheme'),
            self._get_first_header(':authority'),
            self._get_first_header(':path'),
        )

        LOG.info('wsgi app starts: %s %s %s://%s%s', *log_args)

        try:
            app = await self._session._application(
                self._make_environ(),
                self._start_response,
            )

            try:
                if hasattr(app, '__aiter__'):
                    async for data in app:
                        self._write(data)
                else:
                    for data in app:
                        self._write(data)

            finally:
                if hasattr(app, 'close'):
                    await app.close()

        except Exception:
            LOG.exception('wsgi app error: %s %s %s://%s%s', *log_args)
            self._session._rst_stream(self._stream_id, NGHTTP2_INTERNAL_ERROR)
            raise

        finally:
            await self._response_body.close()

        LOG.info('wsgi app completes: %s %s %s://%s%s', *log_args)

    def _make_environ(self):

        environ = self._session._environ.copy()

        environ['wsgi.input'] = self._request_body

        # Should we wrap ``sys.stderr`` in an async adapter?
        environ['wsgi.errors'] = sys.stderr

        environ['REQUEST_METHOD'] = self._get_first_header(':method')

        parsed_path = urllib.parse.urlsplit(self._get_first_header(':path'))
        environ['PATH_INFO'] = parsed_path.path
        environ['QUERY_STRING'] = parsed_path.query

        for name, values in self._request_headers.items():
            if name == ':authority':
                name = 'host'
            elif name.startswith(':'):
                continue  # Skip other HTTP/2 pseudo-headers.
            name = name.upper().replace('-', '_')
            if name not in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                name = 'HTTP_' + name
            environ[name] = ','.join(values)

        return environ

    def _start_response(self, status, response_headers, exc_info=None):
        if exc_info:
            try:
                if self._response_headers_sent:
                    raise exc_info[1].with_traceback(exc_info[2])
            finally:
                exc_info = None  # Avoid dangling cyclic ref.
        else:
            ASSERT.false(self._response_headers_sent)

        # Get the status code from status line like "200 OK".
        status_code = status.split(maxsplit=1)[0]

        # Own C objects to prevent them from being garbage-collected.
        owner = []

        nvlen = 1 + len(response_headers)
        nva = (nghttp2_nv * nvlen)()
        _set_nv(nva[0], b':status', status_code.encode(ENCODING), owner)
        for i, (name, value) in enumerate(response_headers):
            name = name.encode(ENCODING)
            value = value.encode(ENCODING)
            _set_nv(nva[i + 1], name, value, owner)

        # By default, ``nghttp2_submit_response`` makes a copy of input
        # strings, and thus it is fine to free input strings (those in
        # ``owner``) after ``nghttp2_submit_response`` returns.
        nghttp2_submit_response(
            self._session._session,
            self._stream_id,
            nva,
            nvlen,
            ctypes.byref(DATA_PROVIDER),
        )

        self._response_headers_sent = True

        return self._write

    # According to WSGI spec, ``write`` is only intended for maintaining
    # backward compatibility; so let's declare it as not ``async`` for
    # the ease of use.
    def _write(self, data):
        ASSERT.true(self._response_headers_sent)
        self._response_body.write_nonblocking(data)
        if self._response_body_deferred:
            self._response_body_deferred = False
            nghttp2_session_resume_data(
                self._session._session,
                self._stream_id,
            )
        # Unblock ``_handle_outgoing``.
        self._session._outgoing_event.set()

    #
    # Stream life-cycle.
    #

    def set_header(self, name, value):
        ASSERT.none(self._task)
        self._request_headers[name.decode(ENCODING)].extend(
            v.decode(ENCODING) for v in value.split(b'\x00')
        )

    def end_request_headers(self):
        self._start_wsgi_task()

    def write_request_body(self, data):
        self._request_body.write_nonblocking(data)

    def end_request(self):
        self._request_body.close_nonblocking()
        if not self._task:
            self._start_wsgi_task()

    def read_response_body(self, length):
        ASSERT.not_none(self._task)
        data = self._response_body.read_nonblocking(length)
        if data is None:
            self._response_body_deferred = True
        return data

    def close(self):
        if self._task:
            self._task.cancel()


def _set_nv(nv, name, value, owner):
    nv.name = _bytes_to_void_ptr(name, owner)
    nv.namelen = len(name)
    nv.value = _bytes_to_void_ptr(value, owner)
    nv.valuelen = len(value)
    nv.flags = NGHTTP2_NV_FLAG_NONE


def _bytes_to_void_ptr(byte_string, owner):
    buffer = ctypes.create_string_buffer(byte_string, len(byte_string))
    # Because we return only address of the buffer, we have to keep a
    # reference to the buffer (in the ``owner``), or else it will be
    # garbage-collected.
    owner.append(buffer)
    return address_of(buffer)
