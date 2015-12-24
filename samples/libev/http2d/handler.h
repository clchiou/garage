#ifndef HTTP2D_HANDLER_H_
#define HTTP2D_HANDLER_H_

#include <stdbool.h>

#include <ev.h>

#include "lib/bus.h"

struct handler {
	struct bus *bus;
	struct ev_loop *loop;
};

bool handler_init(struct handler *handler, struct bus *bus, struct ev_loop *loop);

#endif
