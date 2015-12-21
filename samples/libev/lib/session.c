#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <ev.h>

#include "base.h"
#include "buffer.h"
#include "bus.h"
#include "channels.h"
#include "helpers.h"
#include "session.h"


#define session_debug(format, ...) \
	debug("[%d] " format, session->fd, ## __VA_ARGS__)

#define session_info(format, ...) \
	info("[%d] " format, session->fd, ## __VA_ARGS__)

#define session_error(format, ...) \
	error("[%d] " format, session->fd, ## __VA_ARGS__)


enum {
	RECV_BUFFER_SIZE = 4096,
	RECV_BUFFER_HIGH_WATERMARK = RECV_BUFFER_SIZE,  // No buffering at recv-side.
	SEND_BUFFER_SIZE = 4096,
	SEND_BUFFER_LOW_WATERMARK = 0,  // No buffering at send-side.
};


static void _recv(struct ev_loop *loop, struct ev_io *watcher, int revents);
static void _send(struct ev_loop *loop, struct ev_io *watcher, int revents);


bool session_init(struct session *session, int socket_fd, struct bus *bus, struct ev_loop *loop)
{
	debug("[%d] init session", socket_fd);

	memset(session, 0, sizeof(*session));

	session->fd = socket_fd;

	session->bus = bus;
	session->loop = loop;

	ev_io_init(&session->recv_watcher, _recv, session->fd, EV_READ);
	ev_io_init(&session->send_watcher, _send, session->fd, EV_WRITE);

	buffer_alloc(&session->recv_buffer, RECV_BUFFER_SIZE);
	buffer_alloc(&session->send_buffer, SEND_BUFFER_SIZE);

	ev_io_start(session->loop, &session->recv_watcher);

	session->remote_address = expect(strdup(stringify_address(session->fd)));

	return true;
}


void session_del(struct session *session)
{
	session_info("close connection %s", session->remote_address);

	ev_io_stop(session->loop, &session->recv_watcher);
	ev_io_stop(session->loop, &session->send_watcher);

	buffer_free(&session->recv_buffer);
	buffer_free(&session->send_buffer);

	close(session->fd);

	free(session->remote_address);

	bool predicate(struct bus *bus, struct bus_message *message, void *predicate_data)
	{
		return message->channel == CHANNEL_DATA_RECEIVED && message->data == predicate_data;
	}
	bus_cancel_messages(session->bus, predicate, session);

	if (!bus_anycast(session->bus, CHANNEL_SESSION_DELETED, session))
		abort();
}


ssize_t session_recv(struct session *session, void *buffer, size_t count)
{
	ssize_t nread = buffer_outgoing_mem(&session->recv_buffer, buffer, count);

	if (buffer_used_space(&session->recv_buffer) <= RECV_BUFFER_HIGH_WATERMARK) {
		// Check ev_is_active() so that logs are less cluttered.
		if (!ev_is_active(&session->recv_watcher)) {
			session_debug("re-enable receiving data");
		}
		ev_io_start(session->loop, &session->recv_watcher);
	}

	return nread;
}


ssize_t session_send(struct session *session, const void *buffer, size_t count)
{
	ssize_t nwrite = buffer_incoming_mem(&session->send_buffer, buffer, count);

	if (buffer_used_space(&session->send_buffer) > SEND_BUFFER_LOW_WATERMARK) {
		// Check ev_is_active() so that logs are less cluttered.
		if (!ev_is_active(&session->send_watcher)) {
			session_debug("start flushing out send_buffer");
		}
		ev_io_start(session->loop, &session->send_watcher);
	}

	return nwrite;
}


static void _recv(struct ev_loop *loop, struct ev_io *watcher, int revents)
{
	struct session *session = container_of(watcher, struct session, recv_watcher);
	session_debug("_recv()");

	while (!buffer_is_full(&session->recv_buffer)) {
		ssize_t nread;
		while ((nread = buffer_incoming_net(&session->recv_buffer, watcher->fd)) == -1 && errno == EINTR)
			;

		if (nread == 0) {
			session_debug("close connection");
			session_del(session);
			return;
		}

		if (nread != -1)
			continue;

		if (errno == EAGAIN || errno == EWOULDBLOCK)
			break;

		if (errno == ECONNRESET) {
			session_debug("connection reset by peer");
			session_del(session);
			return;
		}

		session_error("buffer_incoming_net(): %s", strerror(errno));
		session_del(session);
		return;
	}

	if (buffer_is_full(&session->recv_buffer)) {
		session_debug("stop receiving data");
		ev_io_stop(session->loop, &session->recv_watcher);
	}

	if (!bus_broadcast(session->bus, CHANNEL_DATA_RECEIVED, session))
		abort();
}


static void _send(struct ev_loop *loop, struct ev_io *watcher, int revents)
{
	struct session *session = container_of(watcher, struct session, send_watcher);
	session_debug("_send()");

	while (!buffer_is_empty(&session->send_buffer)) {
		ssize_t nwrite;
		while ((nwrite = buffer_outgoing_net(&session->send_buffer, watcher->fd)) == -1 && errno == EINTR)
			;

		if (nwrite != -1)
			continue;

		if (errno == EAGAIN || errno == EWOULDBLOCK)
			break;

		if (errno == ECONNRESET || errno == EPIPE) {
			session_debug("connection reset by peer");
			session_del(session);
			return;
		}

		session_error("buffer_outgoing_net(): %s", strerror(errno));
		session_del(session);
		return;
	}

	if (buffer_is_empty(&session->send_buffer)) {
		session_debug("send_buffer is empty");
		ev_io_stop(session->loop, &session->send_watcher);
	}
}
