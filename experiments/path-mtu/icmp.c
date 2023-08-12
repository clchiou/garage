#define _DEFAULT_SOURCE

#include <netinet/in.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

#include "common.h"

int main(int argc, char* argv[])
{
	srandom(1); // Use a fixed random seed.

	struct sockaddr_in peer_endpoint;
	ENSURE(argc == 2);
	ENSURE(parse_endpoint(argv[1], "0", &peer_endpoint));

	int sock_fd = 0;
	// `socket(AF_INET, SOCK_DGRAM, IPPROTO_ICMP)` is an (undocumented?) [Linux API].
	//
	// [Linux API]: https://github.com/torvalds/linux/commit/c319b4d76b9e583a5d88d6bf190e079c4e43213d
	TRY(sock_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_ICMP));
	TRY(setsockopt_int(sock_fd, SOL_IP, IP_MTU_DISCOVER, IP_PMTUDISC_PROBE));
	TRY(setsockopt_int(sock_fd, SOL_IP, IP_RECVERR, 1));

	probe_path_mtu(sock_fd, &peer_endpoint, ICMP_HEADER_SIZE, icmp_send);

	TRY(close(sock_fd));

	return 0;
}
