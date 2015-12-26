#include <stdint.h>
#include <string.h>

#include <nghttp2/nghttp2.h>

#include "Python.h"
#include "http2/lib.h"
#include "http2/http2.h"


int session_init(struct session *session, void *http_session)
{
	debug("init session %p", session);

	memset(session, 0, sizeof(*session));

	int error_code = 0;

	session->http_session = http_session;

	nghttp2_session_callbacks *callbacks;
	if ((error_code = get_callbacks(&callbacks)) != 0)
		goto unwind_callbacks;

	if ((error_code = nghttp2_session_server_new(&session->nghttp2_session, callbacks, session)) != 0)
		goto unwind_session;

	return 0;

unwind_session:
	// Fall through.
unwind_callbacks:
	memset(session, 0, sizeof(*session));
	return error_code;
}


void session_del(struct session *session)
{
	if (!session->nghttp2_session)
		return;

	debug("delete session %p", session);

	nghttp2_session_del(session->nghttp2_session);

	// Make repeated calls of session_del() safe.
	memset(session, 0, sizeof(*session));
}


ssize_t session_recv(struct session *session, const uint8_t *data, size_t size)
{
	debug("session %p: recv %zu bytes", session, size);
	return nghttp2_session_mem_recv(session->nghttp2_session, data, size);
}


// Per-stream watchdogs.


// Unit: seconds.
const float SETTINGS_TIMEOUT = 10;
const float RECV_TIMEOUT = 10;
const float SEND_TIMEOUT = 10;


int settings_watchdog_id(int32_t stream_id) { return stream_id * 10 + 0; }
int recv_watchdog_id(int32_t stream_id) { return stream_id * 10 + 1; }
int send_watchdog_id(int32_t stream_id) { return stream_id * 10 + 2; }


void settings_timeout(int watchdog_id, void *user_data)
{
	struct session *session = user_data;
#ifndef NDEBUG
	int32_t stream_id = watchdog_id / 10;
	debug("session %p stream %d: settings timeout", session, stream_id);
#endif
	http_session_close(session->http_session);
}


void recv_timeout(int watchdog_id, void *user_data)
{
	struct session *session = user_data;
#ifndef NDEBUG
	int32_t stream_id = watchdog_id / 10;
	debug("session %p stream %d: recv timeout", session, stream_id);
#endif
	http_session_close(session->http_session);
}


void send_timeout(int watchdog_id, void *user_data)
{
	struct session *session = user_data;
#ifndef NDEBUG
	int32_t stream_id = watchdog_id / 10;
	debug("session %p stream %d: send timeout", session, stream_id);
#endif
	http_session_close(session->http_session);
}
