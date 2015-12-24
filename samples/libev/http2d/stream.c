#include <ev.h>
#include <nghttp2/nghttp2.h>

#include "lib/base.h"

#include "http2d/http-session.h"
#include "http2d/stream.h"


static const float RECV_TIMEOUT = 10;
static const float SEND_TIMEOUT = 10;


static void _timeout(struct stream *stream)
{
	struct http_session *session = stream->session;
	debug("[%d] stream %d timeout", session->id, stream->id);

	ev_timer_stop(session->loop, &stream->recv_timer);
	ev_timer_stop(session->loop, &stream->send_timer);

	expect(check(nghttp2_submit_rst_stream(
				session->nghttp2_session,
				NGHTTP2_FLAG_NONE,
				stream->id,
				NGHTTP2_INTERNAL_ERROR),
			nghttp2_strerror) == 0);

	http_session_shutdown(session, 0);
}


bool stream_init(struct stream *stream, int32_t id, struct http_session *session)
{
	debug("[%d] init stream %d", session->id, id);

	stream->id = id;
	stream->session = session;

	void recv_timeout(struct ev_loop *loop, struct ev_timer *timer, int revents)
	{
		_timeout(container_of(timer, struct stream, recv_timer));
	}
	ev_timer_init(&stream->recv_timer, recv_timeout, 0.0, RECV_TIMEOUT);

	void send_timeout(struct ev_loop *loop, struct ev_timer *timer, int revents)
	{
		_timeout(container_of(timer, struct stream, send_timer));
	}
	ev_timer_init(&stream->send_timer, send_timeout, 0.0, SEND_TIMEOUT);

	return true;
}


void stream_del(struct stream *stream)
{
	struct http_session *session = stream->session;
	debug("[%d] delete stream %d", session->id, stream->id);

	ev_timer_stop(session->loop, &stream->recv_timer);
	ev_timer_stop(session->loop, &stream->send_timer);
}


void stream_start_recv_timer(struct stream *stream)
{
	struct http_session *session = stream->session;
	debug("[%d] start recv timer for stream %d", session->id, stream->id);
	ev_timer_again(session->loop, &stream->recv_timer);
}


void stream_extend_recv_timer(struct stream *stream)
{
	ev_timer_again(stream->session->loop, &stream->recv_timer);
}


void stream_stop_recv_timer(struct stream *stream)
{
	struct http_session *session = stream->session;
	debug("[%d] stop recv timer for stream %d", session->id, stream->id);
	ev_timer_stop(session->loop, &stream->recv_timer);
}


void stream_start_send_timer(struct stream *stream)
{
	struct http_session *session = stream->session;
	debug("[%d] start send timer for stream %d", session->id, stream->id);
	ev_timer_again(session->loop, &stream->send_timer);
}


void stream_extend_send_timer(struct stream *stream)
{
	ev_timer_again(stream->session->loop, &stream->send_timer);
}


void stream_stop_send_timer(struct stream *stream)
{
	struct http_session *session = stream->session;
	debug("[%d] stop send timer for stream %d", session->id, stream->id);
	ev_timer_stop(session->loop, &stream->send_timer);
}
