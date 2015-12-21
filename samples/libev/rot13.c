#include <stdio.h>
#include <signal.h>

#include <ev.h>

#include "lib/base.h"
#include "lib/bus.h"
#include "lib/channels.h"
#include "lib/server.h"


void rot13_handler(struct bus *bus, bus_channel channel, void *user_data, void *data);


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

	if (!bus_register(&bus, CHANNEL_DATA_RECEIVED, rot13_handler, NULL)) {
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

	// Probably no need to release resource at this point...

	return 0;
}
