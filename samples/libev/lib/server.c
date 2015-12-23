#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/socket.h>
#include <sys/types.h>

#include <ev.h>

#include "lib/base.h"
#include "lib/bus.h"
#include "lib/channels.h"
#include "lib/helpers.h"
#include "lib/list.h"
#include "lib/server.h"
#include "lib/session.h"


struct session_handle {
	struct server *server;
	struct list list;
	struct session session;
};


static void _accept(struct ev_loop *loop, struct ev_io *watcher, int revents);


static void _deleted(struct bus *bus, int channel, void *user_data, void *data);


bool server_init(struct server *server, const char *port, struct bus *bus, struct ev_loop *loop)
{
	debug("init server on port %s", port);

	memset(server, 0, sizeof(struct server));

	int fd;
	char address[64];
	if (!prepare_server(port, &fd, address, sizeof(address))) {
		return false;
	}

	if (!bus_register(bus, CHANNEL_SESSION_DELETED, _deleted, NULL)) {
		return false;
	}

	server->bus = bus;

	ev_io_init(&server->watcher, _accept, fd, EV_READ);
	ev_io_start(loop, &server->watcher);

	info("listen on %s", address);

	return true;
}


static void _accept(struct ev_loop *loop, struct ev_io *watcher, int revents)
{
	struct server *server = container_of(watcher, struct server, watcher);

	while (1) {
		int fd = accept(watcher->fd, NULL, NULL);
		if (fd == -1) {
			if (errno != EAGAIN && errno != EWOULDBLOCK) {
				error("accept(): %s", strerror(errno));
			}
			break;
		}

		if (!set_fd_nonblock(fd)) {
			close(fd);
			continue;
		}

		int v = 1;
		if (check(setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &v, (socklen_t)sizeof(v))) == -1) {
			close(fd);
			continue;
		}

		struct session_handle *handle = expect(malloc(
				sizeof(struct session_handle) +
				server->user_session_size));
		if (!session_init(&handle->session, fd, server->bus, loop)) {
			free(handle);
			close(fd);
			continue;
		}

		list_insert(&server->sessions, memset(&handle->list, 0, sizeof(struct list)));

		handle->server = server;

		info("accept %s", handle->session.remote_address);
	}
}


static void _deleted(struct bus *bus, int channel, void *user_data, void *data)
{
	struct session *session = data;
	debug("remove session %d from server", session->fd);
	struct session_handle *handle = container_of(session, struct session_handle, session);
	struct server *server = handle->server;
	list_remove(&server->sessions, &handle->list);
	free(handle);
}
