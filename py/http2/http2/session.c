#include <string.h>

#include <nghttp2/nghttp2.h>

#include "http2/http2.h"


int session_init(struct session *session)
{
	memset(session, 0, sizeof(*session));

	int error_code = 0;

	nghttp2_session_callbacks *callbacks;
	if ((error_code = get_callbacks(&callbacks)) != 0)
		goto unwind_callbacks;

	if ((error_code = nghttp2_session_server_new(&session->session, callbacks, session)) != 0)
		goto unwind_session;

	return 0;

unwind_session:
	// Fall through.
unwind_callbacks:
	return error_code;
}


void session_del(struct session *session)
{
	if (!session->session)
		return;

	nghttp2_session_del(session->session);

	memset(session, 0, sizeof(*session));
}
