#include <stdlib.h>
#include <string.h>

#include <nghttp2/nghttp2.h>

#include "lib/base.h"
#include "lib/bus.h"
#include "lib/session.h"
#include "lib/view.h"

#include "http2d/channels.h"
#include "http2d/http-session.h"
#include "http2d/stream.h"


#define session_debug(format, ...) \
	debug("[%d] " format, session->id, ## __VA_ARGS__)

#define session_error(format, ...) \
	error("[%d] " format, session->id, ## __VA_ARGS__)


static int _stream_close(nghttp2_session *nghttp2_session,
		int32_t stream_id, uint32_t error_code,
		void *user_data)
{
	struct http_session *session = user_data;
	session_debug("close stream %d", stream_id);

	struct session *base_session = container_of(user_data, struct session, user_session);
	session_flush_send_buffer(base_session);

	struct stream *stream = expect(http_session_pop_stream(session, stream_id));
	stream_del(stream);
	free(stream);

	return 0;
}


static void _prepare_response(struct http_session *session, struct stream *stream)
{
	stream_stop_recv_timer(stream);
	expect(bus_broadcast(session->bus, CHANNEL_STREAM_PREPARE_RESPONSE, stream));
}


static int _frame_recv(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		void *user_data)
{
	struct http_session *session = user_data;
	session_debug("recv frame on stream %d", frame->hd.stream_id);

	switch (frame->hd.type) {
	case NGHTTP2_DATA:
		{
			struct stream *stream = http_session_get_stream(
				session, frame->hd.stream_id);
			if (!stream)
				return 0;

			// TODO: Handle POST data.

			if (frame->hd.flags & NGHTTP2_FLAG_END_STREAM)
				_prepare_response(session, stream);
			else
				stream_extend_recv_timer(stream);
			break;
		}
	case NGHTTP2_HEADERS:
		{
			struct stream *stream = http_session_get_stream(
				session, frame->hd.stream_id);
			if (!stream)
				return 0;

			// TODO: HTTP 100-continue

			if (frame->hd.flags & NGHTTP2_FLAG_END_STREAM)
				_prepare_response(session, stream);
			else
				stream_extend_recv_timer(stream);
			break;
		}
	case NGHTTP2_SETTINGS:
		if (frame->hd.flags & NGHTTP2_FLAG_ACK)
			http_session_stop_settings_timer(session);
		break;
	default:
		session_debug("ignore frame of type %d", frame->hd.type);
		break;
	}

	return 0;
}


static int _data_chunk_recv(nghttp2_session *nghttp2_session,
		uint8_t flags, int32_t stream_id,
		const uint8_t *data, size_t len,
		void *user_data)
{
	struct http_session *session = user_data;
	session_debug("receive data chunk on stream %d", stream_id);

	struct stream *stream = http_session_get_stream(session, stream_id);
	if (!stream)
		return 0;

	// TODO: Handle POST data.

	stream_extend_recv_timer(stream);

	return 0;
}


static ssize_t _send(nghttp2_session *nghttp2_session,
		const uint8_t *data, size_t length,
		int flags, void *user_data)
{
	struct session *session = container_of(user_data, struct session, user_session);
	ssize_t nwrite = session_send(session, data, length);
	debug("[%d] send %zd bytes of http data",
			((struct http_session *)user_data)->id, nwrite);
	if (nwrite == 0)
		return NGHTTP2_ERR_WOULDBLOCK;
	else if (nwrite < 0)
		return NGHTTP2_ERR_CALLBACK_FAILURE;
	else
		return nwrite;
}


static int _frame_send(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		void *user_data)
{
	struct http_session *session = user_data;
	session_debug("send frame on stream %d", frame->hd.stream_id);

	switch (frame->hd.type) {
	case NGHTTP2_DATA:
		// Fall through.
	case NGHTTP2_HEADERS:
		{
			struct stream *stream = http_session_get_stream(
					session, frame->hd.stream_id);
			if (!stream)
				return 0;

			if (frame->hd.flags & NGHTTP2_FLAG_END_STREAM) {
				stream_stop_send_timer(stream);
			} else if (nghttp2_session_get_stream_remote_window_size(
						session->nghttp2_session,
						frame->hd.stream_id) <= 0 ||
					nghttp2_session_get_remote_window_size(
						session->nghttp2_session) <= 0) {
				// If stream is blocked by flow control, enable
				// write timeout.
				stream_extend_recv_timer_if_pending(stream);
				stream_start_send_timer(stream);
			} else {
				stream_extend_recv_timer_if_pending(stream);
				stream_stop_send_timer(stream);
			}

			break;
		}
	case NGHTTP2_PUSH_PROMISE:
		// TODO: Implement push promise.
		session_error("push promise is not implemented yet");
		break;
	default:
		session_debug("ignore frame of type %d", frame->hd.type);
		break;
	}

	return 0;
}


static int _send_data(nghttp2_session *nghttp2_session,
		nghttp2_frame *frame, const uint8_t *framehd,
		size_t length, nghttp2_data_source *source,
		void *user_data)
{
	enum {
		HEADER_SIZE = 9,
	};

	struct session *base_session = container_of(user_data, struct session, user_session);

	size_t padlen = frame->data.padlen;
	expect(padlen <= 256);

	size_t size = HEADER_SIZE + padlen + length;
#ifndef NDEBUG
	struct http_session *session = user_data;
	session_debug("send %zu bytes to remote peer on stream %d", size, frame->hd.stream_id);
#endif

	struct rw_view view = session_send_buffer_view(base_session);
	if (size > view.size) {
		session_flush_send_buffer(base_session);
		return NGHTTP2_ERR_WOULDBLOCK;
	}

	uint8_t *p = view.data;

	memcpy(p, framehd, HEADER_SIZE);
	p += HEADER_SIZE;

	if (padlen > 0) {
		*p++ = (uint8_t)(padlen - 1);
	}

	if (length) {
		// TODO: Read `length` bytes from data source.
		memset(p, 0, length);
		p += length;
	}

	if (padlen > 1) {
		memset(p, 0, padlen - 1);
		p += padlen - 1;
	}

	expect(p - view.data == (ssize_t)size);
	session_send_buffer_provided(base_session, size);

	return 0;
}


static int _begin_headers(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		void *user_data)
{
	struct http_session *session = user_data;
	session_debug("begin headers on stream %d", frame->hd.stream_id);

	if (frame->hd.type != NGHTTP2_HEADERS || frame->headers.cat != NGHTTP2_HCAT_REQUEST) {
		session_debug("frame is not header: type=%d category=%d",
				frame->hd.type, frame->headers.cat);
		return 0;
	}

	struct stream *stream = expect(malloc(sizeof(struct stream)));
	expect(stream_init(stream, frame->hd.stream_id, session));
	stream_start_recv_timer(stream);
	http_session_put_stream(session, stream);

	return 0;
}


static int _header(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		const uint8_t *name, size_t namelen,
		const uint8_t *value, size_t valuelen,
		uint8_t flags,
		void *user_data)
{
	struct http_session *session = user_data;
	session_debug("header on stream %d: \"%s\"=\"%s\"", frame->hd.stream_id, name, value);

	// TODO: Construct request object.

	return 0;
}


nghttp2_session_callbacks *http_callbacks(void)
{
	static nghttp2_session_callbacks *callbacks;
	if (!callbacks) {
		if (check(nghttp2_session_callbacks_new(&callbacks), nghttp2_strerror) != 0)
			return NULL;

		nghttp2_session_callbacks_set_on_stream_close_callback(
				callbacks, _stream_close);

		nghttp2_session_callbacks_set_on_frame_recv_callback(
				callbacks, _frame_recv);
		nghttp2_session_callbacks_set_on_data_chunk_recv_callback(
				callbacks, _data_chunk_recv);

		nghttp2_session_callbacks_set_send_callback(
				callbacks, _send);
		nghttp2_session_callbacks_set_on_frame_send_callback(
				callbacks, _frame_send);
		nghttp2_session_callbacks_set_send_data_callback(
				callbacks, _send_data);

		nghttp2_session_callbacks_set_on_begin_headers_callback(
				callbacks, _begin_headers);
		nghttp2_session_callbacks_set_on_header_callback(
				callbacks, _header);
	}
	return callbacks;
}
