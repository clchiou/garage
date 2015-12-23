#ifndef HTTP_SESSION_H_
#define HTTP_SESSION_H_

#include <stdbool.h>
#include <stdint.h>

#include <nghttp2/nghttp2.h>

#include "lib/hash-table.h"
#include "lib/view.h"

enum {
	STREAM_HASH_TABLE_SIZE = 39,
};

struct http_session {
	int id;
	nghttp2_session *nghttp2_session;
	union {
		struct hash_table streams;
		uint8_t blob[hash_table_size(STREAM_HASH_TABLE_SIZE)];
	};
};

bool http_session_init(struct http_session *http_session, int id);

void http_session_del(struct http_session *http_session);

ssize_t http_session_mem_recv(struct http_session *http_session,
		struct ro_view view);

#endif
