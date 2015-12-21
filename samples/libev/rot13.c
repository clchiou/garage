#include <ctype.h>
#include <stdint.h>
#include <stdio.h>
#include <signal.h>

#include <ev.h>

#include "lib/base.h"
#include "lib/bus.h"
#include "lib/channels.h"
#include "lib/server.h"
#include "lib/session.h"


static void _sigint(struct ev_loop *loop, struct ev_io *watcher, int revents)
{
	info("SIGINT");
	ev_unloop(loop, EVUNLOOP_ALL);
}


void _data_received(struct bus *bus, bus_channel channel, void *user_data, void *data)
{
	struct session *session = data;
	debug("[%d] data received", session->fd);

	while (1) {
		uint8_t buffer[1024];
		ssize_t nread = session_recv(session, buffer, sizeof(buffer));
		if (nread <= 0) {
			break;
		}

		for (ssize_t i = 0; i < nread; i++) {
			if (islower(buffer[i]))
				buffer[i] = (buffer[i] - 'a' + 13) % 26 + 'a';
			if (isupper(buffer[i]))
				buffer[i] = (buffer[i] - 'A' + 13) % 26 + 'A';
		}

		ssize_t nwrite = session_send(session, buffer, nread);
		if (nwrite <= 0 || nwrite < nread) {
			error("[%d] drop data", session->fd);
			break;
		}
	}
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

	if (!bus_register(&bus, CHANNEL_DATA_RECEIVED, _data_received, NULL)) {
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
