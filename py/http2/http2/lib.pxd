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

    struct builder:
        pass

    struct response_bookkeeping:
        pass

    int session_init(session *session, void *http_session)
    void session_del(session *session)

    int session_maybe_send(session *session)
    ssize_t session_recv(session *session, const uint8_t *data, size_t size)

    int32_t stream_submit_push_promise(session *session, int32_t stream_id, builder *resposne)
    int stream_submit_response(
            session *session,
            int32_t stream_id,
            builder *resposne,
            response_bookkeeping **bookkeeping)

    void stream_close(session *session, int32_t stream_id)

    int builder_init(builder *builder, size_t num_headers)
    void builder_del(builder *builder)

    int builder_add_header(builder *builder,
            uint8_t *name, size_t namelen,
            uint8_t *value, size_t valuelen)

    int builder_set_body(builder *builder,
            const uint8_t *body, size_t body_size)

    void response_bookkeeping_del(response_bookkeeping* bookkeeping)
