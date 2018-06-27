// Test program that resizes a JPEG image.

#include "common.h"

#include <jpeglib.h>

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

	struct jpeg_error_mgr error_manager;
	memset(&error_manager, 0, sizeof(error_manager));

	jpeg_std_error(&error_manager);

	// Initialize decompressor.

	decompressor.err = &error_manager;

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

	compressor.err = &error_manager;

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
	return run_resize(argc, argv, resize);
}
