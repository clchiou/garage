__all__ = [
    'Session',
]

import io
import logging

from .models import Request
from .watchdogs import Watchdog

from libc.stdint cimport uint8_t, int32_t
from cpython.pycapsule cimport PyCapsule_New, PyCapsule_GetPointer

cimport lib


LOG = logging.getLogger(__name__)


class Http2Error(Exception):
    pass


def check(ssize_t error_code):
    if error_code < 0:
        error = <bytes>lib.http2_strerror(error_code)
        raise Http2Error(error.decode('utf-8'))
    return error_code


cdef class Session:

    cdef bint closed
    cdef public object protocol
    cdef object transport
    cdef object buffer
    cdef public dict watchdogs
    cdef public dict requests
    cdef lib.session session

    def __cinit__(self, protocol, transport):
        LOG.debug('open http session')
        self.closed = False
        self.protocol = protocol
        self.transport = transport
        self.buffer = io.BytesIO()
        self.watchdogs = {}
        self.requests = {}
        check(lib.session_init(&self.session, <lib.http_session*>self))

    def __dealloc__(self):
        self.close()

    def write(self, data):
        self.buffer.write(data)

    def flush(self):
        output = self.buffer.getvalue()
        LOG.debug('flush %d bytes of output buffer', len(output))
        self.transport.write(output)
        self.buffer.close()
        self.buffer = io.BytesIO()

    # Called from Protocol

    def submit_push_promise(self, stream_id, request):
        cdef lib.builder c_request
        cdef int32_t promised_stream_id
        check(lib.builder_init(&c_request, len(request.headers)))
        try:
            for name, value in request.headers.items():
                check(lib.builder_add_header(
                    &c_request,
                    <uint8_t*>name, len(name),
                    <uint8_t*>value, len(value),
                ))
            promised_stream_id = lib.stream_submit_push_promise(
                &self.session, stream_id, &c_request)
            check(promised_stream_id)
            self.flush()
            return promised_stream_id
        finally:
            lib.builder_del(&c_request)

    def handle_response(self, stream_id, response):
        cdef lib.builder c_response
        check(lib.builder_init(&c_response, len(response.headers)))
        try:
            for name, value in response.headers.items():
                check(lib.builder_add_header(
                    &c_response,
                    <uint8_t*>name, len(name),
                    <uint8_t*>value, len(value),
                ))
            if response.body is not None:
                check(lib.builder_set_body(
                    &c_response,
                    <uint8_t *>response.body, len(response.body),
                ))
            check(lib.stream_submit_response(
                &self.session, stream_id, &c_response))
            self.flush()
        finally:
            lib.builder_del(&c_response)

    def close_stream(self, stream_id):
        lib.stream_close(&self.session, stream_id)

    def close(self):
        if self.closed:
            return
        LOG.debug('close http session')
        self.flush()
        lib.session_del(&self.session)
        for watchdog in self.watchdogs.values():
            watchdog.stop()
        self.watchdogs.clear()
        self.closed = True

    def data_received(self, data):
        cdef const uint8_t *d = data
        cdef ssize_t consumed = check(lib.session_recv(
            &self.session, d, len(data)))
        if consumed != len(data):
            raise Http2Error(
                'drop %d/%d bytes of data', len(data) - consumed, len(data))


cdef public void http_session_close(lib.http_session *http_session):
    session = <object>http_session
    session.close()


cdef public ssize_t http_session_send(
        lib.http_session *http_session, const uint8_t *data, size_t size):
    session = <object>http_session
    cdef bytes data_bytes = data[:size]
    session.write(data_bytes)
    return size


### Watchdog C API ###


ctypedef public void (*watchdog_callback)(int watchdog_id, void *user_data)


class WatchdogCallbackClosure:

    def __init__(self, watchdog_id, callback, user_data):
        self.watchdog_id = watchdog_id
        self.callback = callback
        self.user_data = user_data

    def __call__(self):
        cdef watchdog_callback callback = \
            <watchdog_callback>PyCapsule_GetPointer(self.callback, NULL)
        cdef void *user_data = PyCapsule_GetPointer(self.user_data, NULL)
        callback(self.watchdog_id, user_data)


cdef public int watchdog_add(
        lib.http_session *http_session,
        int watchdog_id,
        float delay,
        watchdog_callback callback, void *user_data):
    session = <object>http_session
    closure = WatchdogCallbackClosure(
        watchdog_id,
        PyCapsule_New(callback, NULL, NULL),
        PyCapsule_New(user_data, NULL, NULL),
    )
    if watchdog_id in session.watchdogs:
        return lib.HTTP2_ERROR_WATCHDOG_ID_DUPLICATED
    session.watchdogs[watchdog_id] = Watchdog(delay, closure)
    return 0


cdef public int watchdog_remove(
        lib.http_session *http_session,
        int watchdog_id):
    session = <object>http_session
    try:
        session.watchdogs.pop(watchdog_id)
    except KeyError:
        return lib.HTTP2_ERROR_WATCHDOG_NOT_FOUND
    else:
        return 0


cdef public bint watchdog_exist(
        lib.http_session *http_session, int watchdog_id):
    session = <object>http_session
    return watchdog_id in session.watchdogs


cdef int watchdog_call(lib.http_session *http_session, int watchdog_id, method):
    session = <object>http_session
    dog = session.watchdogs.get(watchdog_id)
    if dog is None:
        return lib.HTTP2_ERROR_WATCHDOG_NOT_FOUND
    method(dog)
    return 0


cdef public int watchdog_start(
        lib.http_session *http_session, int watchdog_id):
    return watchdog_call(http_session, watchdog_id, Watchdog.start)


cdef public int watchdog_restart(
        lib.http_session *http_session, int watchdog_id):
    return watchdog_call(http_session, watchdog_id, Watchdog.restart)


cdef public int watchdog_stop(
        lib.http_session *http_session, int watchdog_id):
    return watchdog_call(http_session, watchdog_id, Watchdog.stop)


cdef public int watchdog_restart_if_started(
        lib.http_session *http_session, int watchdog_id):
    session = <object>http_session
    dog = session.watchdogs.get(watchdog_id)
    if dog is None:
        return lib.HTTP2_ERROR_WATCHDOG_NOT_FOUND
    if dog.started:
        dog.restart()
    return 0


### Request C API ###


cdef public int request_new(
        lib.http_session *http_session, int32_t stream_id):
    session = <object>http_session
    if stream_id in session.requests:
        return lib.HTTP2_ERROR_STREAM_ID_DUPLICATED
    session.requests[stream_id] = Request(session.protocol)
    return 0


cdef public int request_set_header(
        lib.http_session *http_session, int32_t stream_id,
        const uint8_t *name, size_t namelen,
        const uint8_t *value, size_t valuelen):
    session = <object>http_session
    request = session.requests.get(stream_id)
    if request is None:
        return lib.HTTP2_ERROR_STREAM_ID_NOT_FOUND
    cdef bytes name_bytes = name[:namelen]
    cdef bytes value_bytes = value[:valuelen]
    request.headers[name_bytes] = value_bytes
    return 0


cdef public int request_headers_end(
        lib.http_session *http_session, int32_t stream_id):
    session = <object>http_session
    request = session.requests.get(stream_id)
    if request is None:
        return lib.HTTP2_ERROR_STREAM_ID_NOT_FOUND
    session.protocol.handle_request(stream_id, request)
    return 0


cdef public int request_append_body(
        lib.http_session *http_session, int32_t stream_id,
        const uint8_t *data, size_t length):
    session = <object>http_session
    request = session.requests.get(stream_id)
    if request is None:
        return lib.HTTP2_ERROR_STREAM_ID_NOT_FOUND
    request.write(data[:length])
    return 0


cdef public int request_end(
        lib.http_session *http_session, int32_t stream_id):
    session = <object>http_session
    try:
        request = session.requests.pop(stream_id)
    except KeyError:
        return lib.HTTP2_ERROR_STREAM_ID_NOT_FOUND
    request.close()
    return 0
