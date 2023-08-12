#define _DEFAULT_SOURCE

#include <arpa/inet.h>
#include <assert.h>
#include <errno.h>
#include <linux/errqueue.h>
#include <netinet/in.h>
#include <netinet/ip_icmp.h>
#include <poll.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>

#include "common.h"

const size_t IP_HEADER_SIZE = 20;
const size_t ICMP_HEADER_SIZE = 8;
const size_t UDP_HEADER_SIZE = 8;

const size_t MAX_PROBE_MTU = 1600;

void probe_path_mtu(
	int sock_fd,
	struct sockaddr_in *peer_endpoint,
	size_t header_size,
	void (*probe)(int sock_fd, uint8_t *payload, size_t size, struct sockaddr_in *endpoint)
)
{
	uint8_t probe_data[MAX_PROBE_MTU];
	init_random_array(probe_data, sizeof(probe_data) / sizeof(*probe_data));

	bool have_recv_icmp_mtu_reply = false;
	size_t mtu = MAX_PROBE_MTU;
	while (true) {
		LOG("probe path mtu: %lu\n", mtu);
		assert(IP_HEADER_SIZE + header_size <= mtu && mtu < 65536);
		size_t payload_size = mtu - IP_HEADER_SIZE - header_size;
		probe(sock_fd, probe_data, payload_size, peer_endpoint);

		int revents = poll_socket(sock_fd);
		struct message message;
		if (revents == POLLIN) {
			init_message(&message);
			recv_message(sock_fd, &message, MSG_DONTWAIT);
			ensure_endpoint(&message, peer_endpoint);
			// Ignore received data.
			break;
		} else {
			assert(revents == POLLERR);
			init_message(&message);
			size_t num_bytes_recv = recv_message(sock_fd, &message, MSG_ERRQUEUE);
			// Do not call `ensure_endpoint`, as `ee_origin` might be
			// `SO_EE_ORIGIN_LOCAL`.
			assert(num_bytes_recv <= sizeof(probe_data));
			ENSURE(!memcmp(message.buffer, probe_data, num_bytes_recv));
			ENSURE(message.msg.msg_flags == MSG_ERRQUEUE);
			mtu = get_mtu(&message);
			have_recv_icmp_mtu_reply = true;
		}
	}
	if (have_recv_icmp_mtu_reply) {
		LOG("discover path mtu == %lu\n", mtu);
	} else {
		LOG("discover path mtu >= %lu\n", mtu);
	}
}

void init_random_array(uint8_t *array, size_t size)
{
	for (size_t i = 0; i < size; i++) {
		array[i] = (uint8_t)random();
	}
}

bool parse_endpoint(const char *address_str, const char *port_str, struct sockaddr_in *endpoint)
{
	memset(endpoint, 0, sizeof(*endpoint));

	endpoint->sin_family = AF_INET;

	if (inet_aton(address_str, &endpoint->sin_addr) == 0) {
		return false;
	};

	char *end_ptr = NULL;
	unsigned long int port = strtoul(port_str, &end_ptr, 10);
	if (errno != 0) {
		return false;
	}
	if (!(*port_str && !*end_ptr) || port >= 65536) {
		return false;
	}
	endpoint->sin_port = htons((uint16_t)port);

	return true;
}

void log_sock_extended_err(struct sock_extended_err *error)
{
	const char padding[] = "    ";

	LOG("%see_errno=%u\n", padding, error->ee_errno);
	LOG("%see_origin=%u\n", padding, error->ee_origin);
	LOG("%see_type=%u\n", padding, error->ee_type);
	LOG("%see_code=%u\n", padding, error->ee_code);
	LOG("%see_info=%u\n", padding, error->ee_info);
	LOG("%see_data=%u\n", padding, error->ee_data);

	struct sockaddr *offender = SO_EE_OFFENDER(error);
	if (offender->sa_family == AF_INET) {
		struct sockaddr_in *offender_in = (struct sockaddr_in *)offender;
		LOG(
			"%see_offender=%s:%d\n",
			padding,
			inet_ntoa(offender_in->sin_addr),
			ntohs(offender_in->sin_port)
		);
	}
}

//
// Socket Helpers
//

int setsockopt_int(int sock_fd, int level, int opt, int opt_value)
{
	return setsockopt(sock_fd, level, opt, &opt_value, sizeof(opt_value));
}

void icmp_send(int sock_fd, uint8_t *payload, size_t size, struct sockaddr_in *endpoint)
{
	struct icmphdr header;
	memset(&header, 0, sizeof(header));
	header.type = ICMP_ECHO;
	header.code = 0;
	header.un.echo.id = (uint8_t)random();
	header.un.echo.sequence = 1;

	struct icmp_hasher hasher;
	memset(&hasher, 0, sizeof(hasher));
	update(&hasher, (uint8_t *)&header, sizeof(header));
	update(&hasher, payload, size);
	header.checksum = finish(&hasher);

	struct msghdr msg;
	memset(&msg, 0, sizeof(msg));

	msg.msg_name = endpoint;
	msg.msg_namelen = sizeof(*endpoint);

	struct iovec io_vecs[2];
	memset(io_vecs, 0, sizeof(io_vecs));
	io_vecs[0].iov_base = &header;
	io_vecs[0].iov_len = sizeof(header);
	io_vecs[1].iov_base = payload;
	io_vecs[1].iov_len = size;
	msg.msg_iov = io_vecs;
	msg.msg_iovlen = sizeof(io_vecs) / sizeof(*io_vecs);

	msg.msg_control = NULL;
	msg.msg_controllen = 0;

	ssize_t num_bytes_sent = sendmsg(sock_fd, &msg, 0);
	if (num_bytes_sent == -1) {
		if (errno != EMSGSIZE) {
			perror(__func__);
			exit(EXIT_FAILURE);
		}
	} else {
		ENSURE((size_t)num_bytes_sent == sizeof(header) + size);
	}
}

void udp_send(int sock_fd, uint8_t *payload, size_t size, struct sockaddr_in *endpoint)
{
	ssize_t num_bytes_sent = sendto(
		sock_fd, payload, size, 0, (struct sockaddr *)endpoint, sizeof(*endpoint)
	);
	if (num_bytes_sent == -1) {
		if (errno != EMSGSIZE) {
			perror(__func__);
			exit(EXIT_FAILURE);
		}
	} else {
		ENSURE((size_t)num_bytes_sent == size);
	}
}

int poll_socket(int sock_fd)
{
	struct pollfd poll_fd;
	memset(&poll_fd, 0, sizeof(poll_fd));
	poll_fd.fd = sock_fd;
	poll_fd.events = POLLIN;
	TRY(poll(&poll_fd, 1, -1));
	ENSURE(poll_fd.revents == POLLIN || poll_fd.revents == POLLERR);
	return poll_fd.revents;
}

//
// struct message
//

void init_message(struct message *message)
{
	memset(message, 0, sizeof(*message));

	message->msg.msg_name = &message->endpoint;
	message->msg.msg_namelen = sizeof(message->endpoint);

	message->io_vec.iov_base = &message->buffer;
	message->io_vec.iov_len = sizeof(message->buffer);
	message->msg.msg_iov = &message->io_vec;
	message->msg.msg_iovlen = 1;

	message->msg.msg_control = message->cmsg_buffer;
	message->msg.msg_controllen = sizeof(message->cmsg_buffer);
}

size_t recv_message(int sock_fd, struct message *message, int flags)
{
	ssize_t num_bytes_recv = 0;
	TRY(num_bytes_recv = recvmsg(sock_fd, &message->msg, flags));
	return (size_t)num_bytes_recv;
}

void ensure_endpoint(const struct message *message, const struct sockaddr_in *expect)
{
	ENSURE(message->msg.msg_namelen >= sizeof(*expect));
	if (memcmp(message->msg.msg_name, expect, sizeof(*expect))) {
		struct sockaddr_in *endpoint = (struct sockaddr_in *)message->msg.msg_name;
		LOG(
			"expected endpoint %s:%d: %s:%d\n",
			inet_ntoa(expect->sin_addr),
			ntohs(expect->sin_port),
			inet_ntoa(endpoint->sin_addr),
			ntohs(endpoint->sin_port)
		);
		exit(EXIT_FAILURE);
	}
}

size_t get_mtu(struct message *message)
{
	size_t mtu = 0;
	for (
		struct cmsghdr *cmsg = CMSG_FIRSTHDR(&message->msg);
		cmsg != NULL;
		cmsg = CMSG_NXTHDR(&message->msg, cmsg)
	) {
		if (cmsg->cmsg_level == IPPROTO_IP && cmsg->cmsg_type == IP_RECVERR) {
			ENSURE(cmsg->cmsg_len >= CMSG_LEN(sizeof(struct sock_extended_err)));
			struct sock_extended_err error;
			memcpy(&error, CMSG_DATA(cmsg), sizeof(error));
			if (
				(
					error.ee_errno == EMSGSIZE
					&& error.ee_origin == SO_EE_ORIGIN_LOCAL
					&& error.ee_type == 0
					&& error.ee_code == 0
				)
				|| (
					error.ee_errno == EMSGSIZE
					&& error.ee_origin == SO_EE_ORIGIN_ICMP
					&& error.ee_type == ICMP_DEST_UNREACH
					&& error.ee_code == ICMP_FRAG_NEEDED
				)
			) {
				mtu = error.ee_info;
			} else {
				LOG("errqueue: ip_recverr\n");
				log_sock_extended_err(&error);
				exit(EXIT_FAILURE);
			}
		} else {
			LOG(
				"errqueue: unexpected cmsg: cmsg_level=%d cmsg_type=%d\n",
				cmsg->cmsg_level,
				cmsg->cmsg_type
			);
			exit(EXIT_FAILURE);
		}
	}
	ENSURE(mtu > 0);
	return mtu;
}

//
// struct icmp_hasher
//

void update(struct icmp_hasher *hasher, uint8_t *data, size_t size)
{
	for (size_t i = 0; i < size; i++) {
		uint32_t byte = data[i];
		if (((hasher->offset + i) & 1) == 0) {
			byte <<= 8;
		}
		hasher->checksum += byte;
	}
	hasher->offset += size;
}

uint16_t finish(struct icmp_hasher *hasher)
{
	for (uint32_t carry = hasher->checksum >> 16; carry; carry = hasher->checksum >> 16) {
		hasher->checksum = (hasher->checksum & 0xffff) + carry;
	}
	hasher->checksum = ~hasher->checksum;
	return (uint16_t)hasher->checksum;
}
