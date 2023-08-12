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
	ENSURE(argc == 3);
	ENSURE(parse_endpoint(argv[1], argv[2], &peer_endpoint));

	int sock_fd = 0;
	TRY(sock_fd = socket(AF_INET, SOCK_DGRAM, 0));
	TRY(setsockopt_int(sock_fd, SOL_IP, IP_MTU_DISCOVER, IP_PMTUDISC_PROBE));
	TRY(setsockopt_int(sock_fd, SOL_IP, IP_RECVERR, 1));

	probe_path_mtu(sock_fd, &peer_endpoint, UDP_HEADER_SIZE, udp_send);

	TRY(close(sock_fd));

	return 0;
}
