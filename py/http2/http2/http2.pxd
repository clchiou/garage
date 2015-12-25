cdef extern from 'http2/http2.h':

    const char *http2_strerror(int error_code)

    struct session:
        pass

    int session_init(session *session)

    void session_del(session *session)
