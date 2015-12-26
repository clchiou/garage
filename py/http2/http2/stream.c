#include <stdbool.h>

#include "Python.h"
#include "http2/lib.h"
#include "http2/http2.h"


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
	for (size_t i = 0; i < ARRAY_SIZE(items); i++) {
		int err = watchdog_add(session->http_session,
				items[i].id,
				items[i].timeout, items[i].callback, session);
		if (err)
			return err;
		if (items[i].start) {
			err = watchdog_start(
					session->http_session, items[i].id);
			if (err)
				return err;
		}
	}
	return 0;
}


int stream_on_close(struct session *session, int32_t stream_id)
{
	int ids[] = {
		recv_watchdog_id(stream_id),
		send_watchdog_id(stream_id),
	};
	for (size_t i = 0; i < ARRAY_SIZE(ids); i++) {
		int id = ids[i], err;
		if ((err = watchdog_stop(session->http_session, id)) != 0)
			return err;
		if ((err = watchdog_remove(session->http_session, id)) != 0)
			return err;
	}
	return 0;
}


int stream_on_recv(struct session *session, int32_t stream_id)
{
	int id = recv_watchdog_id(stream_id);
	if (!watchdog_exist(session->http_session, id))
		return 0;
	return watchdog_restart(session->http_session, id);
}
