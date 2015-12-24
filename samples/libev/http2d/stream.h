#ifndef HTTP2D_STREAM_H_
#define HTTP2D_STREAM_H_

#include <stdbool.h>
#include <stdint.h>

#include <ev.h>

struct http_session;

struct stream {
	int32_t id;
	struct http_session *session;
	struct ev_timer recv_timer;
	struct ev_timer send_timer;
};

bool stream_init(struct stream *stream, int32_t id, struct http_session *session);

void stream_del(struct stream *stream);

void stream_start_recv_timer(struct stream *stream);
void stream_extend_recv_timer(struct stream *stream);
void stream_stop_recv_timer(struct stream *stream);

void stream_start_send_timer(struct stream *stream);
void stream_extend_send_timer(struct stream *stream);
void stream_stop_send_timer(struct stream *stream);

#endif
