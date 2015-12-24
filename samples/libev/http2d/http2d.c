#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <ev.h>
#include <nghttp2/nghttp2.h>

#include "lib/base.h"
#include "lib/bus.h"
#include "lib/channels.h"
#include "lib/server.h"
#include "lib/session.h"

#include "http2d/channels.h"
#include "http2d/http-session.h"


static void _initialized(struct bus *bus, int channel, void *user_data, void *data)
{
	struct session *base_session = data;
	struct http_session *session = (struct http_session *)base_session->user_session;
	if (!http_session_init(session, base_session->fd, bus, base_session->loop)) {
		session_del(base_session);
		return;
	}
}


static void _data_received(struct bus *bus, int channel, void *user_data, void *data)
{
	struct session *base_session = data;
	struct http_session *session = (struct http_session *)base_session->user_session;
	struct ro_view view = session_recv_buffer_view(base_session);
	ssize_t consumed = http_session_mem_recv(session, view);
	if (consumed < 0) {
		session_del(base_session);
		return;
	}
	session_recv_buffer_consumed(base_session, consumed);
}


static void _deleting(struct bus *bus, int channel, void *user_data, void *data)
{
	struct session *base_session = data;
	struct http_session *session = (struct http_session *)base_session->user_session;
	http_session_del(session);
}


static void _http_want_write(struct bus *bus, int channel, void *user_data, void *data)
{
	struct http_session *session = data;
	if (check(nghttp2_session_send(session->nghttp2_session), nghttp2_strerror) != 0) {
		struct session *base_session = container_of(data, struct session, user_session);
		session_del(base_session);
		return;
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
	if (!bus_init(&bus, loop))
		return 1;

	if (!bus_register(&bus, CHANNEL_SESSION_INITIALIZED, _initialized, NULL))
		return 1;
	if (!bus_register(&bus, CHANNEL_SESSION_DATA_RECEIVED, _data_received, NULL))
		return 1;
	if (!bus_register(&bus, CHANNEL_SESSION_DELETING, _deleting, NULL))
		return 1;
	if (!bus_register(&bus, CHANNEL_HTTP_SESSION_WANT_WRITE, _http_want_write, NULL))
		return 1;

	struct server server;
	if (!server_init(&server, argv[1], &bus, loop))
		return 1;
	server.user_session_size = sizeof(struct http_session);

	struct ev_signal sigint_watcher;
	ev_signal_init(&sigint_watcher, _sigint, SIGINT);
	ev_signal_start(loop, &sigint_watcher);
	ev_unref(loop);

	debug("enter event loop");
	ev_run(loop, 0);
	debug("exit event loop");

	return 0;
}
