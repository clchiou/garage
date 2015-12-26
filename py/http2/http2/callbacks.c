#include <nghttp2/nghttp2.h>

#include "Python.h"
#include "http2/lib.h"
#include "http2/http2.h"


static int on_frame_recv_callback(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		void *user_data)
{
	return 0;
}


static int on_data_chunk_recv_callback(nghttp2_session *nghttp2_session,
		uint8_t flags,
		int32_t stream_id,
		const uint8_t *data, size_t length,
		void *user_data)
{
	return 0;
}


static int on_begin_headers_callback(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		void *user_data)
{
	struct session *session = user_data;

	if (frame->hd.type != NGHTTP2_HEADERS || frame->headers.cat != NGHTTP2_HCAT_REQUEST)
		return 0;

	int id, err;

	id = recv_watchdog_id(frame->hd.stream_id);
	if ((err = watchdog_add(session->http_session, id, RECV_TIMEOUT, recv_timeout, session)) != 0) {
		debug("watchdog_add(%d): %s", id, http2_strerror(err));
		return NGHTTP2_ERR_CALLBACK_FAILURE;
	}
	if ((err = watchdog_start(session->http_session, id)) != 0) {
		debug("watchdog_start(%d): %s", id, http2_strerror(err));
		return NGHTTP2_ERR_CALLBACK_FAILURE;
	}

	id = send_watchdog_id(frame->hd.stream_id);
	if ((err = watchdog_add(session->http_session, id, RECV_TIMEOUT, recv_timeout, session)) != 0) {
		debug("watchdog_add(%d): %s", id, http2_strerror(err));
		return NGHTTP2_ERR_CALLBACK_FAILURE;
	}

	return 0;
}


static int on_header_callback(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		const uint8_t *name, size_t namelen,
		const uint8_t *value, size_t valuelen,
		uint8_t flags,
		void *user_data)
{
	return 0;
}


static ssize_t on_send_callback(nghttp2_session *nghttp2_session,
		const uint8_t *data, size_t length,
		int flags,
		void *user_data)
{
	return 0;
}


static int on_frame_send_callback(nghttp2_session *nghttp2_session,
		const nghttp2_frame *frame,
		void *user_data)
{
	return 0;
}


static int on_send_data_callback(nghttp2_session *nghttp2_session,
		nghttp2_frame *frame, const uint8_t *framehd,
		size_t length, nghttp2_data_source *source,
		void *user_data)
{
	return 0;
}


static int on_stream_close_callback(nghttp2_session *nghttp2_session,
		int32_t stream_id,
		uint32_t error_code,
		void *user_data)
{
	struct session *session = user_data;

	int ids[] = {
		recv_watchdog_id(stream_id),
		send_watchdog_id(stream_id),
	};
	for (size_t i = 0; i < ARRAY_SIZE(ids); i++) {
		int id = ids[i], err;
		if ((err = watchdog_stop(session->http_session, id)) != 0) {
			debug("watchdog_stop(%d): %s", id, http2_strerror(err));
			return NGHTTP2_ERR_CALLBACK_FAILURE;
		}
		if ((err = watchdog_remove(session->http_session, id)) != 0) {
			debug("watchdog_remove(%d): %s", id, http2_strerror(err));
			return NGHTTP2_ERR_CALLBACK_FAILURE;
		}
	}

	return 0;
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
