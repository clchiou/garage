#ifndef COMMON_H_
#define COMMON_H_

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#define LOG(MESSAGE, ...) \
	fprintf(stderr, "%s: %d: " MESSAGE "\n", __FILE__, __LINE__, ##__VA_ARGS__)

typedef bool (*image_resize_func)(
		const void *image,
		size_t image_size,
		size_t new_width,
		const char *output_path);

int run_resize(int argc, char *argv[], image_resize_func resize);

#endif  // COMMON_H_
