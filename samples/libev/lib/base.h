#ifndef BASE_H_
#define BASE_H_

#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define log(level, format, ...)				\
	fprintf(stderr, #level " %s:%d " format "\n",	\
	        __FILE__, __LINE__, ## __VA_ARGS__)

#ifdef NDEBUG
#define debug(...)
#else
#define debug(format, ...) log(DEBUG, format, ## __VA_ARGS__)
#endif

#define info(format, ...) log(INFO, format, ## __VA_ARGS__)

#define error(format, ...) log(ERROR, format, ## __VA_ARGS__)


#define expect(expr)				\
({						\
	typeof(expr) __v = (expr);		\
	if (!__v) {				\
		error("expect: %s", #expr);	\
		abort();			\
	}					\
	__v;					\
})

#define _check_1(expr)						\
({								\
	typeof(expr) __r = (expr);				\
	if (__r == -1) {					\
		error("%s: %s", #expr, strerror(errno));	\
	}							\
	__r;							\
})

#define _check_2(expr, strerror_)				\
({								\
	typeof(expr) __r = (expr);				\
	if (__r < 0) {						\
		error("%s: %s", #expr, (strerror_)(__r));	\
	}							\
	__r;							\
})

#define _select2(_A, _B, name, ...) name
#define check(...) \
	_select2(__VA_ARGS__, _check_2, _check_1)(__VA_ARGS__)


#define container_of(ptr, type, member)				\
({								\
	const typeof(((type *)0)->member) *__mptr = (ptr);	\
	(type *)((char *)__mptr - offsetof(type, member));	\
})


#define ARRAY_SIZE(a)						\
	((sizeof(a) / sizeof(*(a))) /				\
	 (size_t)(!(sizeof(a) % sizeof(*(a)))))


#define zalloc(size)					\
({							\
	size_t __size = (size);				\
	memset(expect(malloc(__size)), 0, __size);	\
})


#define min(a, b)			\
({					\
	const typeof(a) __a = (a);	\
	const typeof(b) __b = (b);	\
	__a < __b ? __a : __b;		\
})


#endif
