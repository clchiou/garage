#include <stdlib.h>
#include <string.h>

#include <nghttp2/nghttp2.h>

#include "Python.h"
#include "http2/lib.h"
#include "http2/http2.h"


static int on_frame_recv_callback(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		void *user_data)
{
	struct session *session = user_data;

	switch (frame->hd.type) {
	case NGHTTP2_DATA:
		// TODO: Handle POST data.
		return stream_on_data_frame(session, frame);
	case NGHTTP2_HEADERS:
		// TODO: HTTP 100-continue
		return stream_on_headers_frame(session, frame);
	case NGHTTP2_SETTINGS:
		if (frame->hd.flags & NGHTTP2_FLAG_ACK) {
			int err = session_settings_ack(session);
			if (err) {
				debug("session %p stream %d: settings ack: %s",
						session, frame->hd.stream_id,
						http2_strerror(err));
				return NGHTTP2_ERR_CALLBACK_FAILURE;
			}
		}
		break;
	}

	return 0;
}


static int on_data_chunk_recv_callback(nghttp2_session *nghttp2_session,
		uint8_t flags,
		int32_t stream_id,
		const uint8_t *data, size_t length,
		void *user_data)
{
	struct session *session = user_data;

	// TODO: Handle POST data.

	return stream_on_data_chunk(session, stream_id);
}


static int on_begin_headers_callback(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		void *user_data)
{
	if (frame->hd.type != NGHTTP2_HEADERS || frame->headers.cat != NGHTTP2_HCAT_REQUEST)
		return 0;

	struct session *session = user_data;
	int32_t stream_id = frame->hd.stream_id;

	int err;
	if ((err = request_new(session->http_session, stream_id)) != 0) {
		debug("session %p stream %d: request_new(): %s",
				session, stream_id, http2_strerror(err));
		return NGHTTP2_ERR_CALLBACK_FAILURE;
	}

	return stream_on_open(session, stream_id);
}


static int on_header_callback(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		const uint8_t *name, size_t namelen,
		const uint8_t *value, size_t valuelen,
		uint8_t flags,
		void *user_data)
{
	struct session *session = user_data;
	int32_t stream_id = frame->hd.stream_id;
	int err = request_set_header(session->http_session, stream_id,
			name, namelen, value, valuelen);
	if (err) {
		debug("session %p stream %d: request_set_header(): %s",
				session, stream_id, http2_strerror(err));
		return NGHTTP2_ERR_CALLBACK_FAILURE;
	}
	return 0;
}


static ssize_t on_send_callback(nghttp2_session *nghttp2_session,
		const uint8_t *data, size_t length,
		int flags,
		void *user_data)
{
	struct session *session = user_data;
	debug("session %p: send %zu bytes", session, length);
	ssize_t nwrite = http_session_send(session->http_session, data, length);
	if (nwrite == 0)
		return NGHTTP2_ERR_WOULDBLOCK;
	else if (nwrite < 0)
		return NGHTTP2_ERR_CALLBACK_FAILURE;
	else
		return nwrite;
}


static int on_frame_send_callback(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		void *user_data)
{
	struct session *session = user_data;

	switch (frame->hd.type) {
	case NGHTTP2_DATA:
		// Fall through.
	case NGHTTP2_HEADERS:
		return stream_on_send_frame(session, frame);
	case NGHTTP2_PUSH_PROMISE:
		// TODO: Implement PUSH PROMISE.
		break;
	}

	return 0;
}


static int on_send_data_callback(nghttp2_session *nghttp2_session,
		nghttp2_frame *frame, const uint8_t *framehd,
		size_t length, nghttp2_data_source *source,
		void *user_data)
{
	enum {
		HEADER_SIZE = 9,
	};

	struct session *session = user_data;

	size_t padlen = frame->data.padlen;
	expect(padlen <= 256);

	size_t size = HEADER_SIZE + padlen + length;
	debug("session %p stream %d: send %zu bytes",
			session, frame->hd.stream_id, size);

	uint8_t blob[256];
	uint8_t *buffer = size <= sizeof(blob) ? blob : malloc(size);
	expect(buffer != NULL);
	uint8_t *pos = buffer;

	memcpy(pos, framehd, HEADER_SIZE);
	pos += HEADER_SIZE;

	if (padlen > 0)
		*pos++ = (uint8_t)(padlen - 1);

	if (length) {
		// TODO: Read length bytes from data source.
		memset(pos, 0, length);
		pos += length;
	}

	if (padlen > 1) {
		memset(pos, 0, padlen - 1);
		pos += padlen - 1;
	}

	expect(pos - buffer == (ssize_t)size);

	ssize_t nwrite = http_session_send(session->http_session, buffer, size);
	if (buffer != blob)
		free(buffer);
	if (nwrite == 0)
		return NGHTTP2_ERR_WOULDBLOCK;
	else if (nwrite < (ssize_t)size)
		return NGHTTP2_ERR_CALLBACK_FAILURE;
	else
		return 0;
}


static int on_stream_close_callback(nghttp2_session *nghttp2_session,
		int32_t stream_id,
		uint32_t error_code,
		void *user_data)
{
	struct session *session = user_data;
	return stream_on_close(session, stream_id);
}


int get_callbacks(nghttp2_session_callbacks **callbacks_out)
{
	static nghttp2_session_callbacks *callbacks;
	if (!callbacks) {
		int error_code = nghttp2_session_callbacks_new(&callbacks);
		if (error_code)
			return error_code;

		nghttp2_session_callbacks_set_on_frame_recv_callback(
				callbacks, on_frame_recv_callback);
		nghttp2_session_callbacks_set_on_data_chunk_recv_callback(
				callbacks, on_data_chunk_recv_callback);

		nghttp2_session_callbacks_set_on_begin_headers_callback(
				callbacks, on_begin_headers_callback);
		nghttp2_session_callbacks_set_on_header_callback(
				callbacks, on_header_callback);

		nghttp2_session_callbacks_set_send_callback(
				callbacks, on_send_callback);
		nghttp2_session_callbacks_set_on_frame_send_callback(
				callbacks, on_frame_send_callback);
		nghttp2_session_callbacks_set_send_data_callback(
				callbacks, on_send_data_callback);

		nghttp2_session_callbacks_set_on_stream_close_callback(
				callbacks, on_stream_close_callback);
	}

	*callbacks_out = callbacks;
	return 0;
}
