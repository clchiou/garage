#include <nghttp2/nghttp2.h>

#include "http2/lib.h"


const char *http2_strerror(int error_code)
{
	switch (error_code) {
#define make_case(e) case e: return #e
		make_case(HTTP2_ERROR);
		make_case(HTTP2_ERROR_RESPONSE_OVERFLOW);
		make_case(HTTP2_ERROR_STREAM_ID_DUPLICATED);
		make_case(HTTP2_ERROR_STREAM_ID_NOT_FOUND);
		make_case(HTTP2_ERROR_WATCHDOG_ID_DUPLICATED);
		make_case(HTTP2_ERROR_WATCHDOG_NOT_FOUND);
#undef make_case
	}
	return nghttp2_strerror(error_code);
}
