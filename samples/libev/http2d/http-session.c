#include <stdlib.h>
#include <string.h>

#include <nghttp2/nghttp2.h>

#include "lib/base.h"
#include "lib/hash-table.h"

#include "http2d/http-session.h"


#define session_debug(format, ...) \
	debug("[%d] " format, session->id, ## __VA_ARGS__)

#define session_error(format, ...) \
	error("[%d] " format, session->id, ## __VA_ARGS__)


static int on_stream_close(nghttp2_session *nghttp2_session,
		int32_t stream_id, uint32_t error_code,
		void *user_data)
{
	return 0;
}


static int on_frame_recv(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		void *user_data)
{
	return 0;
}


static int on_data_chunk_recv(nghttp2_session *nghttp2_session,
		uint8_t flags, int32_t stream_id,
		const uint8_t *data, size_t len,
		void *user_data)
{
	return 0;
}


static int on_frame_send(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		void *user_data)
{
	return 0;
}


static int on_send_data(nghttp2_session *nghttp2_session,
		nghttp2_frame *frame, const uint8_t *framehd,
		size_t length, nghttp2_data_source *source,
		void *user_data)
{
	return 0;
}


static int on_begin_headers(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		void *user_data)
{
	return 0;
}


static int on_header(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		const uint8_t *name, size_t namelen,
		const uint8_t *value, size_t valuelen,
		uint8_t flags,
		void *user_data)
{
	return 0;
}


bool http_session_init(struct http_session *session, int id)
{
	static nghttp2_session_callbacks *callbacks;
	if (!callbacks) {
		if (check(nghttp2_session_callbacks_new(&callbacks), nghttp2_strerror) != 0)
			return false;

		nghttp2_session_callbacks_set_on_stream_close_callback(
				callbacks, on_stream_close);

		nghttp2_session_callbacks_set_on_frame_recv_callback(
				callbacks, on_frame_recv);
		nghttp2_session_callbacks_set_on_data_chunk_recv_callback(
				callbacks, on_data_chunk_recv);

		nghttp2_session_callbacks_set_on_frame_send_callback(
				callbacks, on_frame_send);
		nghttp2_session_callbacks_set_send_data_callback(
				callbacks, on_send_data);

		nghttp2_session_callbacks_set_on_begin_headers_callback(
				callbacks, on_begin_headers);
		nghttp2_session_callbacks_set_on_header_callback(
				callbacks, on_header);
	}

	session->id = id;

	if (check(nghttp2_session_server_new(
				&session->nghttp2_session, callbacks, session),
			nghttp2_strerror) != 0)
		return false;

	size_t stream_id(struct ro_view key) { return *(int32_t *)key.data; }
	if (!hash_table_init(&session->streams, stream_id, STREAM_HASH_TABLE_SIZE))
		return false;

	return true;
}


void http_session_del(struct http_session *session)
{
	struct hash_table_iterator iterator = {0};
	while (hash_table_next(&session->streams, &iterator)) {
		session_debug("delete stream %d", *(int32_t *)iterator.entry->key.data);
		free(iterator.entry->value);
	}
	hash_table_clear(&session->streams);
}


ssize_t http_session_mem_recv(struct http_session *session,
		struct ro_view view)
{
	return check(nghttp2_session_mem_recv(
				session->nghttp2_session, view.data, view.size),
			nghttp2_strerror);
}
