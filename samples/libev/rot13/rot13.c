#include <stdio.h>
#include <stdlib.h>
#include <signal.h>

#include <ev.h>

#include "lib/base.h"
#include "lib/bus.h"
#include "lib/channels.h"
#include "lib/server.h"
#include "lib/session.h"


void rot13_handler(struct bus *bus, bus_channel channel, void *user_data, void *data);


static void _sigint(struct ev_loop *loop, struct ev_io *watcher, int revents)
{
	info("SIGINT");
	ev_unloop(loop, EVUNLOOP_ALL);
}


static void _timer_callback(struct ev_loop *loop, struct ev_timer *timer, int revents)
{
	struct session *session = timer->data;
	debug("[%d] idle timeout", session->fd);

	ev_timer_stop(loop, timer);

	session_flush_send_buffer(session);
}


static void _session_initialized(struct bus *bus, bus_channel channel, void *user_data, void *data)
{
	struct session *session = data;
	debug("[%d] init user session", session->fd);

	struct ev_timer *timer = expect(malloc(sizeof(struct ev_timer)));
	// XXX: At the moment timeout is set for 50 ms, but what's a
	// sensible value?
	ev_timer_init(timer, _timer_callback, 0.0, 0.05);
	timer->data = session;

	session->user_data = timer;
}


static void _session_deleted(struct bus *bus, bus_channel channel, void *user_data, void *data)
{
	struct session *session = data;
	debug("[%d] delete user session", session->fd);

	struct ev_timer *timer = session->user_data;
	ev_timer_stop(session->loop, timer);

	free(timer);
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

	if (!bus_register(&bus, CHANNEL_SESSION_INITIALIZED, _session_initialized, NULL)) {
		return 1;
	}

	if (!bus_register(&bus, CHANNEL_DATA_RECEIVED, rot13_handler, NULL)) {
		return 1;
	}

	struct server server;
	if (!server_init(&server, argv[1], &bus, loop)) {
		return 1;
	}

	// Hack for making sure _session_deleted is called after
	// server's bus message callback :(
	if (!bus_register(&bus, CHANNEL_SESSION_DELETED, _session_deleted, NULL)) {
		return 1;
	}

	struct ev_signal sigint_watcher;
	ev_signal_init(&sigint_watcher, _sigint, SIGINT);
	ev_signal_start(loop, &sigint_watcher);
	ev_unref(loop);

	debug("enter event loop");
	ev_run(loop, 0);
	debug("exit event loop");

	// Probably no need to release resource at this point...

	return 0;
}
