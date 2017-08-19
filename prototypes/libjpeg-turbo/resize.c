// Test program to resize a JPEG image.

#include <errno.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include <jpeglib.h>

#define LOG(MESSAGE, ...) \
	fprintf(stderr, "%s: %d: "  MESSAGE "\n", __FILE__, __LINE__, ##__VA_ARGS__)

#define container_of(ptr, type, member) \
	((type *)((void *)(ptr)) - offsetof(type, member))

struct error_manager {
	struct jpeg_error_mgr jpeg_error_manager;
	jmp_buf setjmp_buffer;
	char error_message[JMSG_LENGTH_MAX];
};

static void error_exit(j_common_ptr common_info)
{
	struct error_manager *error_manager = container_of(
		common_info->err, struct error_manager, jpeg_error_manager);

	common_info->err->output_message(common_info);

	longjmp(error_manager->setjmp_buffer, 1);
}

static void output_message(j_common_ptr common_info)
{
	struct error_manager *error_manager = container_of(
		common_info->err, struct error_manager, jpeg_error_manager);

	if (error_manager->error_message[0]) {
		// Log out the previous error message before we
		// overwrite the error buffer it.
		LOG("previous libjpeg error: %s",
			error_manager->error_message);
	}

	common_info->err->format_message(
		common_info, error_manager->error_message);
}

bool resize(const void *image, size_t image_size, size_t new_width,
		const char *output_path)
{
	bool okay = false;

	// Zero-initialize all resources.

	struct jpeg_decompress_struct decompressor;
	memset(&decompressor, 0, sizeof(decompressor));

	FILE *output = NULL;

	struct jpeg_compress_struct compressor;
	memset(&compressor, 0, sizeof(compressor));

	// Initialize error handler.

	struct error_manager error_manager;
	memset(&error_manager, 0, sizeof(error_manager));

	jpeg_std_error(&error_manager.jpeg_error_manager);

	error_manager.jpeg_error_manager.error_exit = error_exit;
	error_manager.jpeg_error_manager.output_message = output_message;

	// Establish setjmp return context.

	if (setjmp(error_manager.setjmp_buffer)) {
		LOG("libjpeg error: %s", error_manager.error_message);
		goto err;
	}

	// Initialize decompressor.

	decompressor.err = &error_manager.jpeg_error_manager;

	jpeg_create_decompress(&decompressor);

	jpeg_mem_src(&decompressor, (unsigned char *)image, image_size);

	if (jpeg_read_header(&decompressor, TRUE) != JPEG_HEADER_OK) {
		LOG("invalid jpeg header");
		goto err;
	}

	decompressor.scale_num = new_width;
	decompressor.scale_denom = decompressor.image_width;

	if (!jpeg_start_decompress(&decompressor)) {
		LOG("cannot start decompress");
		goto err;
	}

	LOG("resize: %u x %u -> %u x %u",
		decompressor.image_width,
		decompressor.image_height,
		decompressor.output_width,
		decompressor.output_height);

	// Initialize output.

	output = fopen(output_path, "w");
	if (output == NULL) {
		LOG("cannot open: %s: %s", output_path, strerror(errno));
		goto err;
	}

	// Initialize compressor.

	compressor.err = &error_manager.jpeg_error_manager;

	jpeg_create_compress(&compressor);

	jpeg_stdio_dest(&compressor, output);

	compressor.image_width = decompressor.output_width;
	compressor.image_height = decompressor.output_height;
	compressor.input_components = decompressor.out_color_components;
	compressor.in_color_space = decompressor.out_color_space;

	jpeg_set_defaults(&compressor);

	jpeg_start_compress(&compressor, TRUE);

	// Start processing.

	int row_stride =
		decompressor.output_width * decompressor.output_components;

	JSAMPARRAY buffer = decompressor.mem->alloc_sarray(
		(j_common_ptr)&decompressor, JPOOL_IMAGE, row_stride, 1);

	while (decompressor.output_scanline < decompressor.output_height) {
		JDIMENSION num_scanlines = jpeg_read_scanlines(
			&decompressor, buffer, 1);
		JDIMENSION num_written = jpeg_write_scanlines(
			&compressor, buffer, num_scanlines);
		if (num_written != num_scanlines) {
			LOG("write only %u of %u scanlines",
				num_written, num_scanlines);
			break;
		}
	}

	okay = compressor.next_scanline >= compressor.image_height;

	// Clean up and return.

	jpeg_finish_compress(&compressor);

	if (!jpeg_finish_decompress(&decompressor)) {
		LOG("cannot finish decompressor");
		okay = false;
	}

err:
	jpeg_destroy_compress(&compressor);

	if (output && fclose(output)) {
		LOG("cannot close: %s: %s", output_path, strerror(errno));
		okay = false;
	}

	jpeg_destroy_decompress(&decompressor);

	return okay;
}

int main(int argc, char *argv[])
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

	size_t image_size = stat.st_size;
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

	// Guess the image format.

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
