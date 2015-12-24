#include <string.h>

#include <ev.h>
#include <nghttp2/nghttp2.h>

#include "lib/base.h"
#include "lib/bus.h"
#include "lib/session.h"

#include "http2d/channels.h"
#include "http2d/handler.h"
#include "http2d/http-session.h"
#include "http2d/stream.h"


static void _prepare_response(struct bus *bus, int channel, void *user_data, void *data)
{
	//struct handler *handler = user_data;
	struct stream *stream = data;
	struct http_session *session = stream->session;

	debug("[%d] prepare response to stream %d", session->id, stream->id);

	nghttp2_nv response[] = {
		{
			.name = (uint8_t *)":status",
			.namelen = strlen(":status"),
			.value = (uint8_t *)"200",
			.valuelen = strlen("200"),
			.flags = 0,
		},
	};

	nghttp2_data_provider provider;
	memset(&provider, 0, sizeof(nghttp2_data_provider));

	if (check(nghttp2_submit_response(
				session->nghttp2_session,
				stream->id,
				response, ARRAY_SIZE(response),
				&provider),
			nghttp2_strerror) != 0) {
		http_session_shutdown(session, NGHTTP2_INTERNAL_ERROR);
	}

	http_session_check_want_write(session);

	struct session *base_session = container_of((void *)session, struct session, user_session);
	session_flush_send_buffer(base_session);
}


bool handler_init(struct handler *handler, struct bus *bus, struct ev_loop *loop)
{
	memset(handler, 0, sizeof(struct handler));

	handler->bus = bus;
	handler->loop = loop;

	if (!bus_register(handler->bus, CHANNEL_STREAM_PREPARE_RESPONSE, _prepare_response, handler))
		return false;

	return true;
}
