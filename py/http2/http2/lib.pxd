cdef extern from 'http2/lib.h':

    enum:
        HTTP2_ERROR
        HTTP2_ERROR_WATCHDOG_ID_DUPLICATED
        HTTP2_ERROR_WATCHDOG_NOT_FOUND

    const char *http2_strerror(int error_code)

    struct session:
        pass

    int session_init(session *session)

    void session_del(session *session)
