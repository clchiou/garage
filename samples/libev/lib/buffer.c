#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/types.h>

#include "base.h"
#include "buffer.h"


typedef ssize_t (*generic_read)(void *source, void *buffer, size_t count);
typedef ssize_t (*generic_write)(void *source, const void *buffer, size_t count);


void buffer_alloc(struct buffer *buffer, size_t size)
{
	expect(buffer && !buffer->buffer);
	memset(buffer, 0, sizeof(*buffer));
	buffer->buffer = expect(malloc(size));
	buffer->size = size;
}


void buffer_free(struct buffer *buffer)
{
	expect(buffer);
	free(buffer->buffer);
	memset(buffer, 0, sizeof(*buffer));
}


size_t buffer_used_space(struct buffer *buffer)
{
	expect(buffer && buffer->outgoing <= buffer->incoming);
	return buffer->incoming - buffer->outgoing;
}


bool buffer_is_full(struct buffer *buffer)
{
	expect(buffer && buffer->incoming <= buffer->size);
	return buffer->incoming == buffer->size;
}


bool buffer_is_empty(struct buffer *buffer)
{
	return buffer_used_space(buffer) == 0;
}


static size_t buffer_incoming(struct buffer *buffer, generic_read generic_read, void *source)
{
	expect(buffer && buffer->incoming <= buffer->size);

	size_t available = buffer->size - buffer->incoming;
	if (available == 0)
		return 0;

	ssize_t nread = generic_read(source, buffer->buffer + buffer->incoming, available);
	if (nread != -1)
		buffer->incoming += nread;

	return nread;
}


ssize_t buffer_incoming_net(struct buffer *buffer, int fd)
{
	ssize_t _read(void *source, void *buffer, size_t count)
	{
		return read(*(int *)source, buffer, count);
	}
	return buffer_incoming(buffer, _read, &fd);
}


ssize_t buffer_incoming_mem(struct buffer *buffer, const void *buf, size_t count)
{
	struct args {
		const void *buf;
		size_t count;
	} args = {
		.buf = buf,
		.count = count,
	};
	ssize_t _read(void *source, void *buffer, size_t count)
	{
		struct args *args = (struct args *)source;
		ssize_t nread = count < args->count ? count : args->count;
		memmove(buffer, args->buf, nread);
		return nread;
	}
	return buffer_incoming(buffer, _read, &args);
}


static ssize_t buffer_outgoing(struct buffer *buffer, generic_write generic_write, void *source)
{
	expect(buffer && buffer->outgoing <= buffer->incoming);

	size_t available = buffer->incoming - buffer->outgoing;
	if (available == 0) {
		buffer->outgoing = buffer->incoming = 0;
		return 0;
	}

	ssize_t nwrite = generic_write(source, buffer->buffer + buffer->outgoing, available);
	if (nwrite != -1)
		buffer->outgoing += nwrite;
	if (buffer->outgoing == buffer->incoming)
		buffer->outgoing = buffer->incoming = 0;

	return nwrite;
}


ssize_t buffer_outgoing_net(struct buffer *buffer, int fd)
{
	ssize_t _write(void *source, const void *buffer, size_t count)
	{
		return send(*(int *)source, buffer, count, MSG_NOSIGNAL);
	}
	return buffer_outgoing(buffer, _write, &fd);
}


ssize_t buffer_outgoing_mem(struct buffer *buffer, void *buf, size_t count)
{
	struct args {
		void *buf;
		size_t count;
	} args = {
		.buf = buf,
		.count = count,
	};
	ssize_t _write(void *source, const void *buffer, size_t count)
	{
		struct args *args = (struct args *)source;
		ssize_t nwrite = count < args->count ? count : args->count;
		memmove(args->buf, buffer, nwrite);
		return nwrite;
	}
	return buffer_outgoing(buffer, _write, &args);
}
