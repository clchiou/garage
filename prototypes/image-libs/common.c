#include "common.h"

int run_resize(int argc, char *argv[], image_resize_func resize)
{
	int ret = 1;

	// Parse command-line arguments.

	if (argc < 4) {
		LOG("usage: %s input new_width output", argv[0]);
		return 1;
	}

	const char *input_path = argv[1];

	int new_width = 0;
	if (sscanf(argv[2], "%d", &new_width) != 1) {
		LOG("new_width is not an integer: %s", argv[2]);
		return 1;
	}
	// Sanity check.
	if (new_width <= 0 || new_width > 4096) {
		LOG("invalid range of new_width: %d", new_width);
		return 1;
	}

	const char *output_path = argv[3];

	// "Zero"-initialize all resources.

	int fd = -1;
	void *image = MAP_FAILED;
	size_t image_size = 0;

	// Initialize fd.

	fd = open(input_path, O_RDONLY);
	if (fd < 0) {
		LOG("cannot open: %s: %s", input_path, strerror(errno));
		goto err;
	}

	// Retrieve input file size.

	struct stat stat;
	if (fstat(fd, &stat) < 0) {
		LOG("cannot fstat: %s: %s", input_path, strerror(errno));
		goto err;
	}

	image_size = stat.st_size;
	// Sanity check.
	if (image_size < 16) {
		LOG("expect image larger than 16 bytes: %zd", image_size);
		goto err;
	}

	// Initialize mmap'ed input image.

	image = mmap(NULL, image_size, PROT_READ, MAP_PRIVATE, fd, 0);
	if (image == MAP_FAILED) {
		LOG("cannot mmap: %s: %s", input_path, strerror(errno));
		goto err;
	}

	// Detect the image format.

	if (!memcmp(image, "\xFF\xD8\xFF", 3)) {
		LOG("find jpeg signature");
	} else if (!memcmp(image, "\x89PNG\r\n\x1A\n", 8)) {
		LOG("find png signature");
	} else if (!memcmp(image, "GIF87a", 6) || !memcmp(image, "GIF89a", 6)) {
		LOG("find gif signature");
	} else {
		LOG("unknown image format");
	}

	// Now, resize the image.

	if (!resize(image, image_size, new_width, output_path)) {
		LOG("cannot resize: %s", input_path);
		goto err;
	}

	ret = 0;

	// Clean up and exit.
err:
	if (image != MAP_FAILED && munmap(image, image_size) < 0) {
		LOG("cannot munmap: %s: %s", input_path, strerror(errno));
		ret = 1;
	}

	if (fd >= 0 && close(fd) < 0) {
		LOG("cannot close: %s: %s", input_path, strerror(errno));
		ret = 1;
	}

	return ret;
}
