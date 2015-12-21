#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/socket.h>
#include <sys/types.h>

#include <ev.h>

#include "base.h"
#include "bus.h"
#include "channels.h"
#include "helpers.h"
#include "server.h"
#include "session.h"


struct session_handle {
	struct session session;
	struct deque deque;
	struct server *server;
};


static void _accept(struct ev_loop *loop, struct ev_io *watcher, int revents);


static void _deleted(struct bus *bus, bus_channel channel, void *user_data, void *data);


bool server_init(struct server *server, const char *port, struct bus *bus, struct ev_loop *loop)
{
	info("init server on port %s", port);

	memset(server, 0, sizeof(struct server));

	int fd;
	if (!prepare_server(port, &fd)) {
		return false;
	}

	if (!bus_register(bus, CHANNEL_SESSION_DELETED, _deleted, NULL)) {
		return false;
	}

	server->bus = bus;

	ev_io_init(&server->watcher, _accept, fd, EV_READ);
	ev_io_start(loop, &server->watcher);

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

		struct session_handle *handle = expect(malloc(sizeof(struct session_handle)));
		if (!session_init(&handle->session, fd, server->bus, loop)) {
			free(handle);
			close(fd);
			continue;
		}

		memset(&handle->deque, 0, sizeof(struct deque));
		deque_enque(&server->session_handles, &handle->deque);

		handle->server = server;

		struct sockaddr addr;
		socklen_t addr_len = sizeof(addr);
		if (check(getpeername(fd, &addr, &addr_len)) == -1) {
			info("accept ?.?.?.?:? (socket=%d)", fd);
		} else {
			info("accept %s", stringify_address(&addr, addr_len));
		}
	}
}


static void _deleted(struct bus *bus, bus_channel channel, void *user_data, void *data)
{
	struct session *session = data;
	debug("remove session %d from server", session->fd);
	struct session_handle *handle = container_of(session, struct session_handle, session);
	struct server *server = handle->server;
	deque_deque(&server->session_handles, &handle->deque);
	free(handle);
}
