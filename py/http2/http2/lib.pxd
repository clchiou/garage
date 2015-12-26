from libc.stdint cimport uint8_t


cdef extern from 'http2/lib.h':

    enum:
        HTTP2_ERROR_WATCHDOG_ID_DUPLICATED
        HTTP2_ERROR_WATCHDOG_NOT_FOUND

    const char *http2_strerror(int error_code)

    struct http_session:
        pass

    struct session:
        pass

    int session_init(session *session, void *http_session)
    void session_del(session *session)

    ssize_t session_recv(session *session, const uint8_t *data, size_t size)
