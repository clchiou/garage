from libc.stdint cimport uint8_t, int32_t


cdef extern from 'http2/lib.h':

    enum:
        HTTP2_ERROR_STREAM_ID_DUPLICATED
        HTTP2_ERROR_STREAM_ID_NOT_FOUND
        HTTP2_ERROR_WATCHDOG_ID_DUPLICATED
        HTTP2_ERROR_WATCHDOG_NOT_FOUND

    const char *http2_strerror(int error_code)

    struct http_session:
        pass

    struct session:
        pass

    struct response:
        pass

    int session_init(session *session, void *http_session)
    void session_del(session *session)

    ssize_t session_recv(session *session, const uint8_t *data, size_t size)

    int stream_submit_response(session *session, int32_t stream_id, response *resposne)

    int response_init(response *response, size_t num_headers)
    void response_del(response *response)

    int response_add_header(response *response,
            uint8_t *name, size_t namelen,
            uint8_t *value, size_t valuelen)
