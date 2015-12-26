#ifndef HTTP2_LIB_H_
#define HTTP2_LIB_H_

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include <nghttp2/nghttp2.h>


#define ARRAY_SIZE(a)				\
	((sizeof(a) / sizeof(*(a))) /		\
	 (size_t)(!(sizeof(a) % sizeof(*(a)))))


#ifdef NDEBUG
#define debug(...)
#else
#define debug(format, ...) \
	fprintf(stderr, "%s:%d " format "\n", __FILE__, __LINE__, ## __VA_ARGS__)
#endif


#define expect(expr)				\
	do {					\
		if (!(expr)) {			\
			debug("%s", #expr);	\
			abort();		\
		}				\
	} while (0)				\


// NOTE: nghttp2_error falls in [-999, -500] range.
enum {
	HTTP2_ERROR = -1,

	HTTP2_ERROR_WATCHDOG_ID_DUPLICATED = -2,
	HTTP2_ERROR_WATCHDOG_NOT_FOUND = -3,
};

const char *http2_strerror(int error_code);


int get_callbacks(nghttp2_session_callbacks **callbacks_out);


struct http_session;


// Intermediary between http_session and nghttp2_session.
struct session {
	struct http_session *http_session;
	nghttp2_session *nghttp2_session;
};

int session_init(struct session *session, void *http_session);
void session_del(struct session *session);

ssize_t session_recv(struct session *session, const uint8_t *data, size_t size);


// Per-stream watchdogs.

extern const float SETTINGS_TIMEOUT;
extern const float RECV_TIMEOUT;
extern const float SEND_TIMEOUT;

int settings_watchdog_id(int32_t stream_id);
int recv_watchdog_id(int32_t stream_id);
int send_watchdog_id(int32_t stream_id);

void settings_timeout(int watchdog_id, void *user_data);
void recv_timeout(int watchdog_id, void *user_data);
void send_timeout(int watchdog_id, void *user_data);

#endif
