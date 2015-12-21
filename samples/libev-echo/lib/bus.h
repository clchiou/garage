#ifndef BUS_H_
#define BUS_H_

#include <stdbool.h>
#include <stdint.h>

#include <ev.h>

#include "deque.h"

typedef uint8_t bus_channel;

enum {
	MAX_CHANNELS = 1 << (sizeof(bus_channel) * 8),
};

struct bus {
	int fds[2];
	struct ev_loop *loop;
	struct deque *recipients[MAX_CHANNELS];
	struct deque *messages;
	struct ev_io watcher;
};

struct bus_recipient;

typedef void (*bus_on_message)(struct bus *bus, bus_channel channel, void *user_data, void *data);

bool bus_init(struct bus *bus, struct ev_loop *loop);

struct bus_recipient *bus_register(struct bus *bus, bus_channel channel, bus_on_message on_message, void *user_data);

bool bus_unregister(struct bus *bus, bus_channel channel, struct bus_recipient *recipient);

bool bus_broadcast(struct bus *bus, bus_channel channel, void *data);

bool bus_anycast(struct bus *bus, bus_channel channel, void *data);

#endif
