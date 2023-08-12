#ifndef _COMMON_H
#define _COMMON_H

#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE
#endif

#include <netinet/in.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

// This header needs to be included after `netinet/in.h`.
#include <linux/errqueue.h>

#define TRY(EXPR) \
	if ((EXPR) == -1) { \
		perror(#EXPR); \
		exit(EXIT_FAILURE); \
	}

#define LOG(...) fprintf(stderr, __VA_ARGS__)

#define ENSURE(EXPR) \
	if (!(EXPR)) { \
		fprintf(stderr, "%s\n", #EXPR); \
		exit(EXIT_FAILURE); \
	}

extern const size_t IP_HEADER_SIZE;
extern const size_t ICMP_HEADER_SIZE;
extern const size_t UDP_HEADER_SIZE;

extern const size_t MAX_PROBE_MTU;

void probe_path_mtu(
	int sock_fd,
	struct sockaddr_in *peer_endpoint,
	size_t header_size,
	void (*probe)(int sock_fd, uint8_t *payload, size_t size, struct sockaddr_in *endpoint)
);

void init_random_array(uint8_t *array, size_t size);

bool parse_endpoint(const char *address_str, const char *port_str, struct sockaddr_in *endpoint);

void log_sock_extended_err(struct sock_extended_err *error);

//
// Socket Helpers
//

int setsockopt_int(int sock_fd, int level, int opt, int opt_value);

void icmp_send(int sock_fd, uint8_t *payload, size_t size, struct sockaddr_in *endpoint);

void udp_send(int sock_fd, uint8_t *payload, size_t size, struct sockaddr_in *endpoint);

// We need to poll the socket because reading from the error queue is always a non-blocking
// operation, as stated in section 2.1.1.5 "Blocking Read" of the [kernel documentation].
//
// [kernel documentation]: https://www.kernel.org/doc/Documentation/networking/timestamping.txt
int poll_socket(int sock_fd);

//
// struct message
//

struct message {
	struct msghdr msg;

	struct sockaddr_storage endpoint;

	struct iovec io_vec;
	uint8_t buffer[65536];

	uint8_t cmsg_buffer[sizeof(struct cmsghdr) + 4096];
};

void init_message(struct message *message);

size_t recv_message(int sock_fd, struct message *message, int flags);

void ensure_endpoint(const struct message *message, const struct sockaddr_in *expect);

size_t get_mtu(struct message *message);

//
// struct icmp_hasher
//

struct icmp_hasher {
	size_t offset;
	uint32_t checksum;
};

void update(struct icmp_hasher *hasher, uint8_t *data, size_t size);

uint16_t finish(struct icmp_hasher *hasher);

#endif // _COMMON_H
