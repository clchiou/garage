#ifndef HTTP2_LIB_H_
#define HTTP2_LIB_H_


#include <nghttp2/nghttp2.h>


// NOTE: nghttp2_error falls in [-999, -500] range.
enum {
	HTTP2_ERROR = -1,

	HTTP2_ERROR_WATCHDOG_ID_DUPLICATED = -2,
	HTTP2_ERROR_WATCHDOG_NOT_FOUND = -3,
};

const char *http2_strerror(int error_code);


int get_callbacks(nghttp2_session_callbacks **callbacks_out);


struct session {
	nghttp2_session *session;
};

int session_init(struct session *session);

void session_del(struct session *session);


#endif
