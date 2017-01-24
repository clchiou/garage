#include <string.h>

#include <ev.h>
#include <nghttp2/nghttp2.h>

#include "lib/base.h"
#include "lib/hash-table.h"
#include "lib/session.h"
#include "lib/view.h"

#include "http2d/channels.h"
#include "http2d/http-session.h"


#define session_debug(format, ...) \
	debug("[%d] " format, session->id, ## __VA_ARGS__)

#define session_error(format, ...) \
	error("[%d] " format, session->id, ## __VA_ARGS__)


static const float SETTINGS_TIMEOUT = 10;


static struct ro_view stream_id_to_hash_key(const int32_t *stream_id)
{
	struct ro_view key = {
		.data = (const void *)stream_id,
		.size = sizeof(*stream_id),
	};
	return key;
}


static int32_t hash_key_to_stream_id(struct ro_view key)
{
	return *(int32_t *)key.data;
}


bool http_session_init(struct http_session *session, int id, struct bus *bus, struct ev_loop *loop)
{
	memset(session, 0, sizeof(struct http_session));

	session->id = id;
	session_debug("init http session");

	session->bus = bus;
	session->loop = loop;

	nghttp2_session_callbacks *callbacks = http_callbacks();
	if (!callbacks)
		return false;

	size_t hash_func(struct ro_view key) { return hash_key_to_stream_id(key); }
	if (!hash_table_init(&session->streams, hash_func, STREAM_HASH_TABLE_SIZE))
		return false;

	if (check(nghttp2_session_server_new(
				&session->nghttp2_session, callbacks, session),
			nghttp2_strerror) != 0)
		return false;

	void settings_timeout(struct ev_loop *loop, struct ev_timer *settings_timer, int revents)
	{
		struct http_session *session = container_of(settings_timer, struct http_session, settings_timer);
		session_debug("settings timeout");
		http_session_shutdown(session, NGHTTP2_SETTINGS_TIMEOUT);
	}
	ev_timer_init(&session->settings_timer, settings_timeout, SETTINGS_TIMEOUT, 0.0);
	ev_timer_start(session->loop, &session->settings_timer);

	// At this point, session is fully initialized...

	nghttp2_settings_entry entries[] = {
		{
			.settings_id = NGHTTP2_SETTINGS_MAX_CONCURRENT_STREAMS,
			.value = 100,
		},
	};
	if (check(nghttp2_submit_settings(session->nghttp2_session,
				NGHTTP2_FLAG_NONE, entries, ARRAY_SIZE(entries)),
			nghttp2_strerror) != 0) {
		http_session_del(session);
		return false;
	}

	http_session_check_want_write(session);

	return true;
}


void http_session_del(struct http_session *session)
{
	session_debug("delete http session");

	ev_timer_stop(session->loop, &session->settings_timer);

	if (session->shutdown_event)
		expect(bus_unregister(session->bus, CHANNEL_SESSION_SEND_BUFFER_EMPTY, session->shutdown_event));

	nghttp2_session_del(session->nghttp2_session);

	struct hash_table_iterator iterator = {0};
	while (hash_table_next(&session->streams, &iterator)) {
		struct stream *stream = iterator.entry->value;
		session_debug("remove stream %d from session", stream->id);
		stream_del(stream);
		free(stream);
	}
	hash_table_clear(&session->streams);

	// Make sure that repeatedly call http_session_del() is okay.
	memset(session, 0, sizeof(struct http_session));
}


static void _send_buffer_empty(struct bus *bus, int channel, void *user_data, void *data)
{
	struct session *base_session = data;
	struct http_session *session = (struct http_session *)base_session->user_session;

	expect(bus_unregister(session->bus, CHANNEL_SESSION_SEND_BUFFER_EMPTY, session->shutdown_event));
	session->shutdown_event = NULL;

	session_del(base_session);
}


void http_session_shutdown(struct http_session *session, uint32_t error_code)
{
	session_debug("shutdown http session with error code %u", error_code);

	if (error_code) {
		expect(check(nghttp2_session_terminate_session(
					session->nghttp2_session, error_code),
				nghttp2_strerror) == 0);
	}

	if (session->shutdown_event) {
		session_debug("shutdown in progress...");
		return;
	}

	http_session_check_want_write(session);

	struct session *base_session = container_of((void *)session, struct session, user_session);
	session_flush_send_buffer(base_session);

	session->shutdown_event = expect(bus_register(
			session->bus, CHANNEL_SESSION_SEND_BUFFER_EMPTY, _send_buffer_empty, NULL));
}


void http_session_stop_settings_timer(struct http_session *session)
{
	session_debug("stop settings timer");
	ev_timer_stop(session->loop, &session->settings_timer);
}


struct stream *http_session_get_stream(struct http_session *session, int32_t stream_id)
{
	return hash_table_get(&session->streams, stream_id_to_hash_key(&stream_id));
}


void http_session_put_stream(struct http_session *session, struct stream *stream)
{
	struct hash_table_entry entry = {
		.key = stream_id_to_hash_key(&stream->id),
		.value = stream,
	};
	expect(!hash_table_put(&session->streams, &entry, NULL));
}


struct stream *http_session_pop_stream(struct http_session *session, int32_t stream_id)
{
	struct hash_table_entry entry;
	expect(hash_table_pop(&session->streams,
			stream_id_to_hash_key(&stream_id),
			&entry));
	return entry.value;
}


ssize_t http_session_mem_recv(struct http_session *session, struct ro_view view)
{
	ssize_t consumed = check(nghttp2_session_mem_recv(
				session->nghttp2_session, view.data, view.size),
			nghttp2_strerror);
	session_debug("recv %zd bytes of http data", consumed);
	return consumed;
}


void http_session_check_want_write(struct http_session *session)
{
	if (nghttp2_session_want_write(session->nghttp2_session))
		expect(bus_broadcast(session->bus, CHANNEL_HTTP_SESSION_WANT_WRITE, session));
}
