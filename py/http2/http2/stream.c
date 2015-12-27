#include <stdbool.h>
#include <string.h>

#include "Python.h"
#include "http2/lib.h"
#include "http2/http2.h"


static ssize_t data_source_read(
		nghttp2_session *session,
		int32_t stream_id,
		uint8_t *buf, size_t length,
		uint32_t *data_flags,
		nghttp2_data_source *source,
		void *user_data)
{
	struct ro_view *view = source->ptr;

	ssize_t count;
	if (view->size <= length) {
		*data_flags |= NGHTTP2_DATA_FLAG_EOF;
		count = view->size;
	} else
		count = length;

	*data_flags |= NGHTTP2_DATA_FLAG_NO_COPY;

	return count;
}


int stream_submit_response(struct session *session, int32_t stream_id,
		struct response *response)
{
	debug("session %p stream %d: submit response", session, stream_id);

	nghttp2_data_provider *data_provider = NULL;
	nghttp2_data_provider dp;
	struct ro_view view;
	if (response->body) {
		view.data = response->body;
		view.size = response->body_size;
		memset(&dp, 0, sizeof(dp));
		dp.source.ptr = &view;
		dp.read_callback = data_source_read;
		data_provider = &dp;
	}

	int err;
	err = nghttp2_submit_response(session->nghttp2_session,
			stream_id,
			response->headers, response->num_headers,
			data_provider);
	if (err)
		return err;

	err = nghttp2_session_send(session->nghttp2_session);
	if (err)
		return err;

	return 0;
}


// Unit: seconds.
static const float RECV_TIMEOUT = 10;
static const float SEND_TIMEOUT = 10;


static void recv_timeout(int watchdog_id, void *user_data)
{
	struct session *session = user_data;
#ifndef NDEBUG
	int32_t stream_id = watchdog_id / 10;
	debug("session %p stream %d: recv timeout", session, stream_id);
#endif
	http_session_close(session->http_session);
}


static void send_timeout(int watchdog_id, void *user_data)
{
	struct session *session = user_data;
#ifndef NDEBUG
	int32_t stream_id = watchdog_id / 10;
	debug("session %p stream %d: send timeout", session, stream_id);
#endif
	http_session_close(session->http_session);
}


int stream_on_open(struct session *session, int32_t stream_id)
{
	struct {
		int id;
		float timeout;
		watchdog_callback callback;
		bool start;
	} items[] = {
		{
			.id = recv_watchdog_id(stream_id),
			.timeout = RECV_TIMEOUT,
			.callback = recv_timeout,
			.start = true,
		},
		{
			.id = send_watchdog_id(stream_id),
			.timeout = SEND_TIMEOUT,
			.callback = send_timeout,
			.start = false,
		},
	};
	int err = 0;
	for (size_t i = 0; i < ARRAY_SIZE(items); i++) {
		int err = watchdog_add(session->http_session,
				items[i].id,
				items[i].timeout, items[i].callback, session);
		if (err)
			break;
		if (items[i].start) {
			err = watchdog_start(session->http_session, items[i].id);
			if (err)
				break;
		}
	}
	if (err) {
		debug("session %p stream %d: stream_on_open(): %s",
				session, stream_id, http2_strerror(err));
		return NGHTTP2_ERR_CALLBACK_FAILURE;
	}
	return 0;
}


int stream_on_close(struct session *session, int32_t stream_id)
{
	int ids[] = {
		recv_watchdog_id(stream_id),
		send_watchdog_id(stream_id),
	};
	int err = 0;
	for (size_t i = 0; i < ARRAY_SIZE(ids); i++) {
		int id = ids[i];
		if ((err = watchdog_stop(session->http_session, id)) != 0)
			break;
		if ((err = watchdog_remove(session->http_session, id)) != 0)
			break;
	}
	if (err) {
		debug("session %p stream %d: stream_on_close(): %s",
				session, stream_id, http2_strerror(err));
		return NGHTTP2_ERR_CALLBACK_FAILURE;
	}
	return 0;
}


static int restart_recv(struct session *session, int32_t stream_id)
{
	int id = recv_watchdog_id(stream_id);
	if (!watchdog_exist(session->http_session, id))
		return 0;
	int err = watchdog_restart(session->http_session, id);
	if (err) {
		debug("session %p stream %d: restart recv watchdog(): %s",
				session, stream_id, http2_strerror(err));
		return NGHTTP2_ERR_CALLBACK_FAILURE;
	}
	return 0;
}


int stream_on_headers_frame(struct session *session, const nghttp2_frame *frame)
{
	int32_t stream_id = frame->hd.stream_id;
	if (frame->hd.flags & NGHTTP2_FLAG_END_STREAM) {
		debug("session %p: stream %d: request end", session, stream_id);
		int err = request_complete(session->http_session, stream_id);
		if (err) {
			debug("session %p stream %d: request_complete(): %s",
					session, stream_id,
					http2_strerror(err));
			return NGHTTP2_ERR_CALLBACK_FAILURE;
		}
		return 0;
	} else
		return restart_recv(session, stream_id);
}


int stream_on_data_frame(struct session *session, const nghttp2_frame *frame)
{
	// Their implementations are the same (at least for now).
	return stream_on_headers_frame(session, frame);
}


int stream_on_data_chunk(struct session *session, int32_t stream_id)
{
	return restart_recv(session, stream_id);
}


static bool is_blocked(struct session *session, const nghttp2_frame *frame)
{
	if (nghttp2_session_get_stream_remote_window_size(
				session->nghttp2_session,
				frame->hd.stream_id) <= 0)
		return true;
	if (nghttp2_session_get_remote_window_size(
				session->nghttp2_session) <= 0)
		return true;
	return false;
}


int stream_on_send_frame(struct session *session, const nghttp2_frame *frame)
{
	int32_t stream_id = frame->hd.stream_id;

	int recv_id = recv_watchdog_id(stream_id);
	if (!watchdog_exist(session->http_session, recv_id))
		return 0;

	int send_id = send_watchdog_id(stream_id);
	expect(watchdog_exist(session->http_session, send_id));

	int err = 0;
	do {
		if (frame->hd.flags & NGHTTP2_FLAG_END_STREAM) {
			if ((err = watchdog_stop(session->http_session, send_id)) != 0)
				break;
		} else if (is_blocked(session, frame)) {
			if ((err = watchdog_restart_if_started(session->http_session, recv_id)) != 0)
				break;
			// Enable send watchdog only when blocked.
			if ((err = watchdog_start(session->http_session, send_id)) != 0)
				break;
		} else {
			if ((err = watchdog_restart_if_started(session->http_session, recv_id)) != 0)
				break;
			if ((err = watchdog_stop(session->http_session, send_id)) != 0)
				break;
		}
	} while (0);

	if (err) {
		debug("session %p stream %d: stream_on_send_frame(): %s",
				session, stream_id, http2_strerror(err));
		return NGHTTP2_ERR_CALLBACK_FAILURE;
	}

	return 0;
}
