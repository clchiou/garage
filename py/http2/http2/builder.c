#include <stdlib.h>
#include <string.h>

#include <nghttp2/nghttp2.h>

#include "http2/lib.h"


int builder_init(struct builder *builder, size_t num_headers)
{
	memset(builder, 0, sizeof(*builder));

	if (num_headers > ARRAY_SIZE(builder->blob)) {
		size_t size = num_headers * sizeof(nghttp2_nv);
		builder->headers = malloc(size);
		memset(builder->headers, 0, size);
	} else
		builder->headers = builder->blob;
	expect(builder->headers != NULL);

	builder->num_headers = num_headers;

	return 0;
}


void builder_del(struct builder *builder)
{
	if (builder->headers != builder->blob)
		free(builder->headers);
	memset(builder, 0, sizeof(*builder));
}


int builder_add_header(struct builder *builder,
		uint8_t *name, size_t namelen,
		uint8_t *value, size_t valuelen)
{
	if (builder->header_pos >= builder->num_headers)
		return HTTP2_ERROR_RESPONSE_OVERFLOW;

	nghttp2_nv *header = &builder->headers[builder->header_pos];
	header->name = name;
	header->namelen = namelen;
	header->value = value;
	header->valuelen = valuelen;
	header->flags = (NGHTTP2_NV_FLAG_NO_COPY_NAME | NGHTTP2_NV_FLAG_NO_COPY_VALUE);

	builder->header_pos++;

	return 0;
}


int builder_set_body(struct builder *builder,
		const uint8_t *body, size_t body_size)
{
	builder->body = body;
	builder->body_size = body_size;
	return 0;
}
