#ifndef LIB_SERVER_H_
#define LIB_SERVER_H_

#include <stdbool.h>

#include <ev.h>

#include "lib/bus.h"
#include "lib/list.h"

struct server {
	struct ev_io watcher;
	struct bus *bus;
	struct list *sessions;
	size_t user_session_size;
};

bool server_init(struct server *server, const char *port, struct bus *bus, struct ev_loop *loop);

#endif
