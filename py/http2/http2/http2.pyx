__all__ = [
    'Session',
]

import asyncio
import logging

from .models import Request, Response
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
    cdef object loop
    cdef public object transport
    cdef object handler
    cdef public dict watchdogs
    cdef public dict requests
    cdef lib.session session

    def __cinit__(self, transport, handler, loop=None):
        LOG.debug('open http session')
        self.closed = False
        self.loop = loop
        self.transport = transport
        self.handler = handler
        self.watchdogs = {}
        self.requests = {}
        check(lib.session_init(&self.session, <lib.http_session*>self))

    def __dealloc__(self):
        self.close()

    def handle_request(self, stream_id, request):
        response = Response()
        loop = self.loop or asyncio.get_event_loop()
        loop.call_soon(self._handle, stream_id, request, response)

    def _handle(self, stream_id, request, response):
        self.handler(request, response)
        cdef lib.response rep
        check(lib.response_init(&rep, len(response.headers)))
        try:
            # Will name and value be garbage-collected after for-loop?
            for name, value in response.headers.items():
                check(lib.response_add_header(
                    &rep,
                    <uint8_t*>name, len(name),
                    <uint8_t*>value, len(value),
                ))
            check(lib.stream_submit_response(&self.session, stream_id, &rep))
        finally:
            lib.response_del(&rep)

    # Called from Http2Protocol

    def close(self):
        if self.closed:
            return
        LOG.debug('close http session')
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
    session.transport.write(data_bytes)
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
    session.requests[stream_id] = Request()
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


cdef public int request_append_body(
        lib.http_session *http_session, int32_t stream_id,
        const uint8_t *data, size_t length):
    session = <object>http_session
    request = session.requests.get(stream_id)
    if request is None:
        return lib.HTTP2_ERROR_STREAM_ID_NOT_FOUND
    request.write(data[:length])
    return 0


cdef public int request_complete(
        lib.http_session *http_session, int32_t stream_id):
    session = <object>http_session
    try:
        request = session.requests.pop(stream_id)
    except KeyError:
        return lib.HTTP2_ERROR_STREAM_ID_NOT_FOUND
    request.close()
    session.handle_request(stream_id, request)
    return 0
