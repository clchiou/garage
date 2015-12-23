#include <stdio.h>
#include <stdlib.h>
#include <signal.h>

#include <ev.h>

#include "lib/base.h"
#include "lib/bus.h"
#include "lib/channels.h"
#include "lib/server.h"
#include "lib/session.h"

#include "http2d/http-session.h"


static void _initialized(struct bus *bus, int channel, void *user_data, void *data)
{
	struct session *session = data;
	debug("[%d] init http session", session->fd);

	struct http_session *http_session = expect(malloc(sizeof(struct http_session)));
	if (!http_session_init(http_session, session->fd)) {
		free(http_session);
		session_del(session);
		return;
	}

	session->user_data = http_session;
}


static void _data_received(struct bus *bus, int channel, void *user_data, void *data)
{
	struct session *session = data;
	debug("[%d] process http data", session->fd);

	struct http_session *http_session = expect(session->user_data);
	struct ro_view view = session_recv_buffer_view(session);
	ssize_t consumed = http_session_mem_recv(http_session, view);
	if (consumed < 0) {
		session_del(session);
		return;
	}
	session_recv_buffer_consumed(session, consumed);
}


static void _deleting(struct bus *bus, int channel, void *user_data, void *data)
{
	struct session *session = data;
	struct http_session *http_session = session->user_data;
	if (http_session) {
		debug("[%d] delete http session", session->fd);
		http_session_del(http_session);
		free(http_session);
	}
}


static void _sigint(struct ev_loop *loop, struct ev_io *watcher, int revents)
{
	info("SIGINT");
	ev_unloop(loop, EVUNLOOP_ALL);
}


int main(int argc, char *argv[])
{
	if (argc < 2) {
		printf("Usage: %s port\n", argv[0]);
		return 1;
	}

	struct ev_loop *loop = expect(ev_default_loop(0));

	struct bus bus;
	if (!bus_init(&bus, loop)) {
		return 1;
	}

	if (!bus_register(&bus, CHANNEL_SESSION_INITIALIZED, _initialized, NULL)) {
		return 1;
	}

	if (!bus_register(&bus, CHANNEL_SESSION_DATA_RECEIVED, _data_received, NULL)) {
		return 1;
	}

	if (!bus_register(&bus, CHANNEL_SESSION_DELETING, _deleting, NULL)) {
		return 1;
	}

	struct server server;
	if (!server_init(&server, argv[1], &bus, loop)) {
		return 1;
	}

	struct ev_signal sigint_watcher;
	ev_signal_init(&sigint_watcher, _sigint, SIGINT);
	ev_signal_start(loop, &sigint_watcher);
	ev_unref(loop);

	debug("enter event loop");
	ev_run(loop, 0);
	debug("exit event loop");

	return 0;
}
