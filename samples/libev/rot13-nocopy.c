#include <ctype.h>
#include <stdint.h>

#include "lib/base.h"
#include "lib/bus.h"
#include "lib/session.h"
#include "lib/view.h"


void rot13_handler(struct bus *bus, bus_channel channel, void *user_data, void *data)
{
	struct session *session = data;
	debug("[%d] data received", session->fd);

	struct ro_view recv_view;
	session_recv_buffer_view(session, &recv_view);

	struct rw_view send_view;
	session_send_buffer_view(session, &send_view);

	size_t size = min(recv_view.size, send_view.size);
	debug("[%d] process %zu bytes", session->fd, size);
	for (size_t i = 0; i < size; i++) {
		uint8_t c = recv_view.data[i];
		if (islower(c))
			c = (c - 'a' + 13) % 26 + 'a';
		else if (isupper(c))
			c = (c - 'A' + 13) % 26 + 'A';
		send_view.data[i] = c;
	}

	session_recv_buffer_consumed(session, size);
	session_send_buffer_provided(session, size);
}
