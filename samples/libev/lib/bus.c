#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "lib/base.h"
#include "lib/bus.h"
#include "lib/helpers.h"
#include "lib/list.h"


static void _on_message(struct ev_loop *loop, struct ev_io *watcher, int revents);


bool bus_init(struct bus *bus, struct ev_loop *loop)
{
	memset(bus, 0, sizeof(struct bus));

	if (check(pipe(bus->fds)) == -1) {
		return false;
	}

	if (!set_fd_nonblock(bus->fds[0]) || !set_fd_nonblock(bus->fds[1])) {
		close(bus->fds[0]);
		close(bus->fds[1]);
		return false;
	}

	ev_io_init(&bus->watcher, _on_message, bus->fds[0], EV_READ);
	ev_io_start(loop, &bus->watcher);

	// Internal events should have highest priority.
	ev_set_priority(&bus->watcher, EV_MAXPRI);

	bus->loop = loop;

	return true;
}


struct bus_recipient *bus_register(struct bus *bus, bus_channel channel, bus_on_message on_message, void *user_data)
{
	struct bus_recipient *recipient = zalloc(sizeof(struct bus_recipient));

	debug("register bus recipient %p to channel %d", recipient, channel);

	recipient->on_message = on_message;
	recipient->user_data = user_data;

	list_insert(&bus->recipients[channel], &recipient->list);

	return recipient;
}


bool bus_unregister(struct bus *bus, bus_channel channel, struct bus_recipient *recipient)
{
	debug("unregister bus recipient %p from channel %d", recipient, channel);

	list_remove(&bus->recipients[channel], &recipient->list);

	return true;
}


void bus_cancel_messages(struct bus *bus, bus_message_predicate predicate, void *predicate_data)
{
	debug("cancel messages");

	for (struct list *list = bus->messages, *next; list; list = next) {
		next = list->next;
		struct bus_message *message = container_of(list, struct bus_message, list);
		if (predicate(bus, message, predicate_data)) {
			list_remove(&bus->messages, list);
			free(message);
		}
	}
}


static bool bus_enqueue_message(struct bus *bus, bus_channel channel, enum message_type type, void *data)
{
	struct bus_message *message = zalloc(sizeof(struct bus_message));

	message->channel = channel;
	message->type = type;
	message->data = data;

	list_insert(&bus->messages, &message->list);

	uint8_t v = 1;
	ssize_t nwrite;
	while ((nwrite = write(bus->fds[1], &v, sizeof(v))) == -1 && errno == EINTR)
		;
	if (nwrite == -1 && errno != EAGAIN && errno != EWOULDBLOCK) {
		error("write(): %s", strerror(errno));
		list_remove(&bus->messages, &message->list);
		free(message);
		return false;
	}

	return true;
}


bool bus_broadcast(struct bus *bus, bus_channel channel, void *data)
{
	return bus_enqueue_message(bus, channel, MESSAGE_BROADCAST, data);
}


bool bus_anycast(struct bus *bus, bus_channel channel, void *data)
{
	return bus_enqueue_message(bus, channel, MESSAGE_ANYCAST, data);
}


static void _do_broadcast(struct bus *bus, bus_channel channel, void *data)
{
	debug("broadcast on channel %d", channel);

	for (struct list *list = bus->recipients[channel]; list; list = list->next) {
		struct bus_recipient *recipient = container_of(list, struct bus_recipient, list);
		recipient->on_message(bus, channel, recipient->user_data, data);
	}
}


static void _do_anycast(struct bus *bus, bus_channel channel, void *data)
{
	debug("anycast on channel %d", channel);

	struct list *list = bus->recipients[channel];
	if (list) {
		struct bus_recipient *recipient = container_of(list, struct bus_recipient, list);
		recipient->on_message(bus, channel, recipient->user_data, data);
	}
}


static void _on_message(struct ev_loop *loop, struct ev_io *watcher, int revents)
{
	struct bus *bus = container_of(watcher, struct bus, watcher);
	debug("on bus message");

	char discard[32];
	while (read(bus->fds[0], discard, sizeof(discard)) != -1)
		;
	if (errno != EAGAIN && errno != EWOULDBLOCK) {
		error("read(): %s", strerror(errno));
		abort();
	}

	// Traverse the message list this way so that it's safe for
	// recipient to enqueue/dequeue message on the fly.
	for (struct list *list; (list = bus->messages) != NULL;) {
		list_remove(&bus->messages, list);
		struct bus_message *message = container_of(list, struct bus_message, list);
		switch (message->type) {
		case MESSAGE_BROADCAST:
			_do_broadcast(bus, message->channel, message->data);
			break;
		case MESSAGE_ANYCAST:
			_do_anycast(bus, message->channel, message->data);
			break;
		default:
			error("unknown message type: %d", message->type);
			abort();
		}
		free(message);
	}
}
