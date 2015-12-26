#include <stdlib.h>
#include <string.h>

#include <nghttp2/nghttp2.h>

#include "http2/lib.h"


int response_init(struct response *response, size_t num_headers)
{
	memset(response, 0, sizeof(*response));

	if (num_headers > ARRAY_SIZE(response->blob)) {
		size_t size = num_headers * sizeof(nghttp2_nv);
		response->headers = malloc(size);
		memset(response->headers, 0, size);
	} else
		response->headers = response->blob;
	expect(response->headers != NULL);

	response->num_headers = num_headers;

	return 0;
}


void response_del(struct response *response)
{
	if (response->headers != response->blob)
		free(response->headers);
	memset(response, 0, sizeof(*response));
}


int response_add_header(struct response *response,
		uint8_t *name, size_t namelen,
		uint8_t *value, size_t valuelen)
{
	if (response->header_pos >= response->num_headers)
		return HTTP2_ERROR_RESPONSE_OVERFLOW;

	nghttp2_nv *header = &response->headers[response->header_pos];
	header->name = name;
	header->namelen = namelen;
	header->value = value;
	header->valuelen = valuelen;
	header->flags = (NGHTTP2_NV_FLAG_NO_COPY_NAME | NGHTTP2_NV_FLAG_NO_COPY_VALUE);

	response->header_pos++;

	return 0;
}
