#ifndef LIB_SESSION_H_
#define LIB_SESSION_H_

#include <ev.h>

#include "lib/base.h"
#include "lib/buffer.h"
#include "lib/bus.h"
#include "lib/view.h"

struct session;

struct session {
	int fd;
	struct bus *bus;
	struct ev_loop *loop;
	struct ev_io recv_watcher;
	struct ev_io send_watcher;
	struct buffer recv_buffer;
	struct buffer send_buffer;
	char *remote_address;
	void *user_data;
};

bool session_init(struct session *session, int socket_fd, struct bus *bus, struct ev_loop *loop);

void session_del(struct session *session);

ssize_t session_recv(struct session *session, void *buffer, size_t count);
ssize_t session_send(struct session *session, const void *buffer, size_t count);

struct ro_view session_recv_buffer_view(struct session *session);
void session_recv_buffer_consumed(struct session *session, size_t size);

struct rw_view session_send_buffer_view(struct session *session);
void session_send_buffer_provided(struct session *session, size_t size);

void session_flush_send_buffer(struct session *session);

#endif
