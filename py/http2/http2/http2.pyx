cimport http2


class Http2Error(Exception):
    pass


cdef check(int error_code):
    if error_code:
        error = <bytes>http2.http2_strerror(error_code)
        raise Http2Error(error.encode('utf-8'))


cdef class Session:

    cdef http2.session session

    def __cinit__(self):
        check(http2.session_init(&self.session))

    def __dealloc__(self):
        http2.session_del(&self.session)
