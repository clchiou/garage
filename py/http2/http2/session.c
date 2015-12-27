#include <stdint.h>
#include <string.h>

#include <nghttp2/nghttp2.h>

#include "Python.h"
#include "http2/lib.h"
#include "http2/http2.h"


enum {
	SETTINGS_WATCHDOG_ID = 0,
	MAX_CONCURRENT_STREAMS = 100,
};

int recv_watchdog_id(int32_t stream_id) { return stream_id * 10 + 1; }
int send_watchdog_id(int32_t stream_id) { return stream_id * 10 + 2; }


// Unit: seconds.
static const float SETTINGS_TIMEOUT = 10;


static void settings_timeout(int watchdog_id, void *user_data)
{
	struct session *session = user_data;
	debug("session %p: settings timeout", session);

	int err;
	err = nghttp2_session_terminate_session(session->nghttp2_session,
			NGHTTP2_SETTINGS_TIMEOUT);
	if (err) {
		debug("session %p nghttp2_session_terminate_session(): %s",
				session, nghttp2_strerror(err));
	}
	err = nghttp2_session_send(session->nghttp2_session);
	if (err) {
		debug("session %p: nghttp2_session_send(): %s",
				session, nghttp2_strerror(err));
	}

	if (session_should_close(session))
		http_session_close(session->http_session);
}


int session_init(struct session *session, void *http_session)
{
	debug("init session %p", session);

	memset(session, 0, sizeof(*session));

	int error_code = 0;

	session->http_session = http_session;

	nghttp2_session_callbacks *callbacks;
	if ((error_code = get_callbacks(&callbacks)) != 0)
		goto unwind_callbacks;

	error_code = nghttp2_session_server_new(
			&session->nghttp2_session, callbacks, session);
	if (error_code)
		goto unwind_session;

	nghttp2_settings_entry entries[] = {
		{
			.settings_id = NGHTTP2_SETTINGS_MAX_CONCURRENT_STREAMS,
			.value = MAX_CONCURRENT_STREAMS,
		},
	};
	error_code = nghttp2_submit_settings(session->nghttp2_session,
			NGHTTP2_FLAG_NONE, entries, ARRAY_SIZE(entries));
	if (error_code)
		goto unwind_settings;

	error_code = nghttp2_session_send(session->nghttp2_session);
	if (error_code)
		goto unwind_settings_send;

	error_code = watchdog_add(session->http_session,
			SETTINGS_WATCHDOG_ID,
			SETTINGS_TIMEOUT, settings_timeout, session);
	if (error_code)
		goto unwind_watchdog_add;

	error_code = watchdog_start(session->http_session,
			SETTINGS_WATCHDOG_ID);
	if (error_code)
		goto unwind_watchdog_start;

	return 0;

unwind_watchdog_start:
	{
		int e = watchdog_remove(session->http_session,
				SETTINGS_WATCHDOG_ID);
		if (e) {
			debug("session %p: watchdog_remove(): %s",
					session, http2_strerror(e));
		}
	}
unwind_watchdog_add:
	// Fall through.
unwind_settings_send:
	// Fall through.
unwind_settings:
	nghttp2_session_del(session->nghttp2_session);
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

	// The settings watchdog is stopped and removed in
	// session_settings_ack().

	// Make repeated calls of session_del() safe.
	memset(session, 0, sizeof(*session));
}


bool session_should_close(struct session *session)
{
	return (nghttp2_session_want_read(session->nghttp2_session) == 0 &&
			nghttp2_session_want_write(session->nghttp2_session) == 0);
}


int session_settings_ack(struct session *session)
{
	debug("session %p: settings ack", session);
	int err;
	err = watchdog_stop(session->http_session, SETTINGS_WATCHDOG_ID);
	if (err)
		return err;
	err = watchdog_remove(session->http_session, SETTINGS_WATCHDOG_ID);
	if (err)
		return err;
	return 0;
}


ssize_t session_recv(struct session *session, const uint8_t *data, size_t size)
{
	debug("session %p: recv %zu bytes", session, size);
	return nghttp2_session_mem_recv(session->nghttp2_session, data, size);
}
