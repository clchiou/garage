from garage.async.watchdogs import Watchdog

from cpython.pycapsule cimport PyCapsule_New, PyCapsule_GetPointer

cimport lib


class Http2Error(Exception):
    pass


cdef check(int error_code):
    if error_code:
        error = <bytes>lib.http2_strerror(error_code)
        raise Http2Error(error.encode('utf-8'))


cdef class Session:

    cdef lib.session session

    def __cinit__(self):
        check(lib.session_init(&self.session))

    def __dealloc__(self):
        lib.session_del(&self.session)


### Watchdog ###


WATCHDOGS = {}
WATCHDOG_ID = 1


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


cdef public int watchdog_new(float delay, watchdog_callback callback, void *user_data):
    global WATCHDOG_ID
    if WATCHDOG_ID in WATCHDOGS:
        return lib.HTTP2_ERROR_WATCHDOG_ID_DUPLICATED
    cdef int watchdog_id = WATCHDOG_ID
    closure = WatchdogCallbackClosure(
        WATCHDOG_ID,
        PyCapsule_New(callback, NULL, NULL),
        PyCapsule_New(user_data, NULL, NULL),
    )
    WATCHDOGS[WATCHDOG_ID] = Watchdog(delay, closure)
    WATCHDOG_ID += 1
    return watchdog_id


cdef int watchdog_call(int watchdog_id, method):
    dog = WATCHDOGS.get(watchdog_id)
    if dog is None:
        return lib.HTTP2_ERROR_WATCHDOG_NOT_FOUND
    method(dog)
    return 0


cdef public int watchdog_start(int watchdog_id):
    return watchdog_call(watchdog_id, Watchdog.start)


cdef public int watchdog_restart(int watchdog_id):
    return watchdog_call(watchdog_id, Watchdog.restart)


cdef public int watchdog_stop(int watchdog_id):
    return watchdog_call(watchdog_id, Watchdog.stop)


cdef public int watchdog_del(int watchdog_id):
    try:
        WATCHDOGS.pop(watchdog_id)
    except KeyError:
        return lib.HTTP2_ERROR_WATCHDOG_NOT_FOUND
    else:
        return 0
