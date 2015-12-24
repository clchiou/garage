#ifndef HTTP2D_HTTP_SESSION_H_
#define HTTP2D_HTTP_SESSION_H_

#include <stdbool.h>
#include <stdint.h>

#include <ev.h>
#include <nghttp2/nghttp2.h>

#include "lib/bus.h"
#include "lib/hash-table.h"
#include "lib/view.h"

#include "http2d/stream.h"

nghttp2_session_callbacks *http_callbacks(void);

enum {
	STREAM_HASH_TABLE_SIZE = 39,
};

struct http_session {
	int id;
	struct bus *bus;
	struct ev_loop *loop;
	nghttp2_session *nghttp2_session;
	struct bus_recipient *shutdown_event;
	struct ev_timer settings_timer;
	union {
		struct hash_table streams;
		uint8_t blob[hash_table_size(STREAM_HASH_TABLE_SIZE)];
	};
};

bool http_session_init(struct http_session *session, int id, struct bus *bus, struct ev_loop *loop);

void http_session_del(struct http_session *session);

void http_session_shutdown(struct http_session *session, uint32_t error_code);

void http_session_stop_settings_timer(struct http_session *session);

struct stream *http_session_get_stream(struct http_session *session, int32_t stream_id);

void http_session_put_stream(struct http_session *session, struct stream *stream);

struct stream *http_session_pop_stream(struct http_session *session, int32_t stream_id);

ssize_t http_session_mem_recv(struct http_session *session, struct ro_view view);

void http_session_check_want_write(struct http_session *session);

#endif
