#include <fcntl.h>
#include <netdb.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/types.h>

#include "lib/base.h"
#include "lib/helpers.h"


enum {
	BACKLOG = 1024,
};


static bool init_socket(struct addrinfo *info, int *socket_fd)
{
	int fd;
	if (check(fd = socket(info->ai_family, info->ai_socktype, info->ai_protocol)) == -1) {
		return false;
	}

	int v = 1;
	if (check(setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &v, (socklen_t)sizeof(v))) == -1) {
		close(fd);
		return false;
	}

	if (!set_fd_nonblock(fd)) {
		close(fd);
		return false;
	}

	if (check(bind(fd, info->ai_addr, info->ai_addrlen)) == -1) {
		close(fd);
		return false;
	}

	if (check(listen(fd, BACKLOG)) == -1) {
		close(fd);
		return false;
	}

	*socket_fd = fd;
	return true;
}


bool prepare_server(const char *port, int *socket_fd, char *address_info, size_t size)
{
	struct addrinfo hints = {0};
	hints.ai_family = AF_INET;
	hints.ai_socktype = SOCK_STREAM;
	hints.ai_flags = AI_PASSIVE;
	hints.ai_protocol = 0;

	struct addrinfo *info;
	if (check(getaddrinfo(NULL, port, &hints, &info), gai_strerror) != 0) {
		return false;
	}

	bool okay = false;

	if (!info) {
		error("no addrinfo");
		goto exit;
	}

	if (info->ai_next) {
		error("multiple addrinfo");
		goto exit;
	}

	okay = init_socket(info, socket_fd);

	strncpy(address_info, stringify_address2(info->ai_addr, info->ai_addrlen), size);
	address_info[size - 1] = '\0';

exit:
	free(info);
	return okay;
}


bool set_fd_nonblock(int fd)
{
	int flags;
	while ((flags = fcntl(fd, F_GETFL, 0)) == -1 && errno == EINTR)
		;
	if (flags == -1) {
		error("fcntl(%d): %s", fd, strerror(errno));
		return false;
	}

	int r;
	while ((r = fcntl(fd, F_SETFL, flags | O_NONBLOCK)) == -1 && errno == EINTR)
		;
	if (r == -1) {
		error("fcntl(%d): %s", fd, strerror(errno));
		return false;
	}

	return true;
}


char *_stringify_address(int sockfd, char *buffer, size_t buffer_size)
{
	struct sockaddr addr;
	socklen_t addr_len = sizeof(addr);
	if (check(getpeername(sockfd, &addr, &addr_len)) == -1) {
		return "?.?.?.?:?";
	} else {
		return _stringify_address2(&addr, addr_len, buffer, buffer_size);
	}
}


char *_stringify_address2(const struct sockaddr *addr, socklen_t addr_len, char *buffer, size_t buffer_size)
{
	char host[NI_MAXHOST];
	char port[NI_MAXSERV];
	if (getnameinfo(addr, addr_len,
			host, sizeof(host), port, sizeof(port),
			NI_NUMERICHOST | NI_NUMERICSERV)) {
		return "?.?.?.?:?";
	} else {
		snprintf(buffer, buffer_size, "%s:%s", host, port);
		return buffer;
	}
}
