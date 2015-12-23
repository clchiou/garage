#ifndef VIEW_H_
#define VIEW_H_

#include <stddef.h>
#include <stdint.h>
#include <string.h>

struct ro_view {
	const uint8_t *data;
	size_t size;
};

struct rw_view {
	uint8_t *data;
	size_t size;
};

#define view_is_null(view) ((view).data == NULL)

#define view_equal(p, q)						\
({									\
	typeof(p) __p = (p);						\
	typeof(q) __q = (q);						\
	__p.size == __q.size && !memcmp(__p.data, __q.data, __p.size);	\
})

#endif
