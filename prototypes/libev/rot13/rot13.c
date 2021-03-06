#include <stdio.h>
#include <signal.h>

#include <ev.h>

#include "lib/base.h"
#include "lib/bus.h"
#include "lib/channels.h"
#include "lib/server.h"
#include "lib/session.h"


void rot13_handler(struct bus *bus, int channel, void *user_data, void *data);


static void _sigint(struct ev_loop *loop, struct ev_io *watcher, int revents)
{
	info("SIGINT");
	ev_unloop(loop, EVUNLOOP_ALL);
}


static void _timer_callback(struct ev_loop *loop, struct ev_timer *timer, int revents)
{
	struct session *session = container_of((void *)timer, struct session, user_session);
	debug("[%d] idle timeout", session->fd);

	ev_timer_stop(loop, timer);

	session_flush_send_buffer(session);
}


static void _session_initialized(struct bus *bus, int channel, void *user_data, void *data)
{
	struct session *session = data;
	debug("[%d] init user session", session->fd);

	// XXX: At the moment timeout is set for 50 ms, but what's a
	// sensible value?
	struct ev_timer *timer = (struct ev_timer *)session->user_session;
	ev_timer_init(timer, _timer_callback, 0.0, 0.05);
}


static void _session_deleting(struct bus *bus, int channel, void *user_data, void *data)
{
	struct session *session = data;
	debug("[%d] delete user session", session->fd);

	struct ev_timer *timer = (struct ev_timer *)session->user_session;
	ev_timer_stop(session->loop, timer);
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

	if (!bus_register(&bus, CHANNEL_SESSION_DATA_RECEIVED, rot13_handler, NULL)) {
		return 1;
	}

	if (!bus_register(&bus, CHANNEL_SESSION_DELETING, _session_deleting, NULL)) {
		return 1;
	}

	struct server server;
	if (!server_init(&server, argv[1], &bus, loop)) {
		return 1;
	}
	server.user_session_size = sizeof(struct ev_timer);

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
