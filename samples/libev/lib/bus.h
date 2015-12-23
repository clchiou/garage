#ifndef BUS_H_
#define BUS_H_

#include <stdbool.h>

#include <ev.h>

#include "lib/list.h"

struct bus;

struct bus_message;

typedef void (*bus_on_message)(struct bus *bus, int channel, void *user_data, void *data);

typedef bool (*bus_message_predicate)(struct bus *bus, struct bus_message *message, void *predicate_data);

enum {
	MAX_CHANNELS = 16,
};

enum message_type {
	MESSAGE_BROADCAST = 1,
	MESSAGE_ANYCAST = 2,
};

struct bus {
	int fds[2];
	struct ev_loop *loop;
	struct list *recipients[MAX_CHANNELS];
	struct list *messages;
	struct ev_io watcher;
};

struct bus_recipient {
	bus_on_message on_message;
	void *user_data;
	struct list list;
};

struct bus_message {
	int channel;
	enum message_type type;
	void *data;
	struct list list;
};

bool bus_init(struct bus *bus, struct ev_loop *loop);

struct bus_recipient *bus_register(struct bus *bus, int channel, bus_on_message on_message, void *user_data);

bool bus_unregister(struct bus *bus, int channel, struct bus_recipient *recipient);

void bus_cancel_messages(struct bus *bus, bus_message_predicate predicate, void *predicate_data);

bool bus_broadcast(struct bus *bus, int channel, void *data);

bool bus_anycast(struct bus *bus, int channel, void *data);

#endif
