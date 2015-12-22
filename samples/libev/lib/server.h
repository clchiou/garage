#ifndef SERVER_H_
#define SERVER_H_

#include <stdbool.h>

#include <ev.h>

#include "lib/bus.h"
#include "lib/deque.h"

struct server {
	struct ev_io watcher;
	struct bus *bus;
	struct deque *session_handles;
};

bool server_init(struct server *server, const char *port, struct bus *bus, struct ev_loop *loop);

#endif
