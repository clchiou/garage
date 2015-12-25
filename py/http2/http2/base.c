#include <nghttp2/nghttp2.h>


const char *http2_strerror(int error_code)
{
	return nghttp2_strerror(error_code);
}
