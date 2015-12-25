#ifndef HTTP2_HTTP2_H_
#define HTTP2_HTTP2_H_

#include <nghttp2/nghttp2.h>

const char *http2_strerror(int error_code);

int get_callbacks(nghttp2_session_callbacks **callbacks_out);

struct session {
	nghttp2_session *session;
};

int session_init(struct session *session);

void session_del(struct session *session);

#endif
