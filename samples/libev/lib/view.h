#ifndef VIEW_H_
#define VIEW_H_

#include <stdint.h>

struct ro_view {
	const uint8_t *data;
	size_t size;
};

struct rw_view {
	uint8_t *data;
	size_t size;
};

#define view_is_null(view) ((view).data == NULL)

#endif
