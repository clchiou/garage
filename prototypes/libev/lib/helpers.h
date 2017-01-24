#ifndef LIB_HELPERS_H_
#define LIB_HELPERS_H_

#include <netdb.h>
#include <stdbool.h>
#include <sys/socket.h>

bool prepare_server(const char *port, int *socket_fd, char *address_info, size_t size);

bool set_fd_nonblock(int fd);

char *_stringify_address(int sockfd, char *buffer, size_t buffer_size);
char *_stringify_address2(const struct sockaddr *addr, socklen_t addr_len, char *buffer, size_t buffer_size);

#define stringify_address(sockfd)					\
({									\
	char __b[NI_MAXHOST + 1 + NI_MAXSERV + 1];			\
	_stringify_address((sockfd), __b, sizeof(__b));			\
})

#define stringify_address2(addr, addr_len)				\
({									\
	char __b[NI_MAXHOST + 1 + NI_MAXSERV + 1];			\
	_stringify_address2((addr), (addr_len), __b, sizeof(__b));	\
})

#endif
