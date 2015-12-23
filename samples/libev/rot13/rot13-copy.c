#include <ctype.h>
#include <stdint.h>

#include "lib/base.h"
#include "lib/bus.h"
#include "lib/session.h"


void rot13_handler(struct bus *bus, int channel, void *user_data, void *data)
{
	struct session *session = data;
	debug("[%d] data received", session->fd);

	while (1) {
		uint8_t buffer[1024];
		ssize_t nread = session_recv(session, buffer, sizeof(buffer));
		if (nread <= 0) {
			break;
		}

		for (ssize_t i = 0; i < nread; i++) {
			if (islower(buffer[i]))
				buffer[i] = (buffer[i] - 'a' + 13) % 26 + 'a';
			else if (isupper(buffer[i]))
				buffer[i] = (buffer[i] - 'A' + 13) % 26 + 'A';
		}

		ssize_t nwrite = session_send(session, buffer, nread);
		if (nwrite <= 0 || nwrite < nread) {
			error("[%d] drop data", session->fd);
			break;
		}
	}

	debug("[%d] reset idle timer", session->fd);
	struct ev_timer *timer = (struct ev_timer *)session->user_session;
	ev_timer_again(session->loop, timer);
}
