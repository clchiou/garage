#ifndef BUFFER_H_
#define BUFFER_H_

#include <stdbool.h>

struct buffer {
	void *buffer;
	size_t incoming;
	size_t outgoing;
	size_t size;
};

void buffer_alloc(struct buffer *buffer, size_t size);
void buffer_free(struct buffer *buffer);

size_t buffer_used_space(struct buffer *buffer);

bool buffer_is_full(struct buffer *buffer);
bool buffer_is_empty(struct buffer *buffer);

ssize_t buffer_incoming_io(struct buffer *buffer, int fd);
ssize_t buffer_incoming_mem(struct buffer *buffer, const void *buf, size_t count);

ssize_t buffer_outgoing_io(struct buffer *buffer, int fd);
ssize_t buffer_outgoing_mem(struct buffer *buffer, void *buf, size_t count);

#endif
