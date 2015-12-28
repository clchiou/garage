#ifndef HTTP2_LIB_H_
#define HTTP2_LIB_H_

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include <nghttp2/nghttp2.h>


#define ARRAY_SIZE(a)				\
	((sizeof(a) / sizeof(*(a))) /		\
	 (size_t)(!(sizeof(a) % sizeof(*(a)))))


#ifdef NDEBUG
#define debug(...)
#else
#define debug(format, ...) \
	fprintf(stderr, "%s:%d " format "\n", __FILE__, __LINE__, ## __VA_ARGS__)
#endif


#define expect(expr)				\
	do {					\
		if (!(expr)) {			\
			debug("%s", #expr);	\
			abort();		\
		}				\
	} while (0)				\


struct ro_view {
	const uint8_t *data;
	size_t size;
};


// NOTE: nghttp2_error falls in [-999, -500] range.
enum {
	HTTP2_ERROR = -1,

	HTTP2_ERROR_RESPONSE_OVERFLOW = -2,

	HTTP2_ERROR_STREAM_ID_DUPLICATED = -3,
	HTTP2_ERROR_STREAM_ID_NOT_FOUND = -4,

	HTTP2_ERROR_WATCHDOG_ID_DUPLICATED = -5,
	HTTP2_ERROR_WATCHDOG_NOT_FOUND = -6,
};

const char *http2_strerror(int error_code);


int get_callbacks(nghttp2_session_callbacks **callbacks_out);


struct http_session;


int settings_watchdog_id(int32_t stream_id);
int recv_watchdog_id(int32_t stream_id);
int send_watchdog_id(int32_t stream_id);


// Intermediary between http_session and nghttp2_session.
struct session {
	struct http_session *http_session;
	nghttp2_session *nghttp2_session;
};

int session_init(struct session *session, void *http_session);
void session_del(struct session *session);

bool session_should_close(struct session *session);

int session_settings_ack(struct session *session);

ssize_t session_recv(struct session *session, const uint8_t *data, size_t size);


struct builder;

int32_t stream_submit_push_promise(struct session *session,
		int32_t stream_id, struct builder *request);

int stream_submit_response(struct session *session,
		int32_t stream_id, struct builder *response);

void stream_close(struct session *session, int32_t stream_id);

int stream_on_open(struct session *session, int32_t stream_id);
int stream_on_close(struct session *session, int32_t stream_id);

int stream_on_headers_frame(struct session *session, const nghttp2_frame *frame);
int stream_on_data_frame(struct session *session, const nghttp2_frame *frame);
int stream_on_data_chunk(struct session *session, int32_t stream_id);

int stream_on_send_frame(struct session *session, const nghttp2_frame *frame);
int stream_on_send_push_promise_frame(struct session *session,
		const nghttp2_frame *frame);


struct builder {
	nghttp2_nv *headers;
	size_t header_pos;
	size_t num_headers;
	const uint8_t *body;
	size_t body_size;
	nghttp2_nv blob[32];
};

int builder_init(struct builder *builder, size_t num_headers);
void builder_del(struct builder *builder);

int builder_add_header(struct builder *builder,
		uint8_t *name, size_t namelen,
		uint8_t *value, size_t valuelen);

int builder_set_body(struct builder *builder,
		const uint8_t *body, size_t body_size);

#endif
