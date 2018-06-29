// Test program that resizes a PNG image.

#include "common.h"

#include <jpeglib.h>
#include <png.h>

struct memory_view {
	const void *data;
	size_t offset;
	size_t size;
};

static void png_read(png_structp png, png_bytep data, png_size_t length)
{
	struct memory_view *view = png_get_io_ptr(png);

	if (view->size - view->offset < length) {
		png_error(png, "png_read: exceed data size");
		return;
	}

	memmove(data, view->data + view->offset, length);
	view->offset += length;
}

static bool resize_png_impl(
		png_structp png, png_infop info,
		struct jpeg_compress_struct *compressor)
{
	bool okay = false;

	png_bytepp rows = NULL;
	png_bytep row_buffer = NULL;

	if (setjmp(png_jmpbuf(png))) {
		LOG("png longjmp");
		goto err;
	}

	png_read_info(png, info);

	const uint32_t width = png_get_image_width(png, info);
	const uint32_t height = png_get_image_height(png, info);
	const uint32_t row_bytes = png_get_rowbytes(png, info);
	LOG("image dimension: %d x %d, %d", width, height, row_bytes);

	const png_byte color_type = png_get_color_type(png, info);
	if (color_type != PNG_COLOR_TYPE_RGB) {
		LOG("does not support color_type: %02x", color_type);
		goto err;
	}

	const png_byte bit_depth = png_get_bit_depth(png, info);
	if (bit_depth != 8) {
		LOG("does not support bit_dipth: %d", bit_depth);
		goto err;
	}

	const png_byte interlace_type = png_get_interlace_type(png, info);
	if (interlace_type != PNG_INTERLACE_NONE) {
		LOG("does not support interlace_type: %d", interlace_type);
		goto err;
	}

	rows = calloc(height, sizeof(png_bytep));
	if (!rows) {
		LOG("cannot allocate rows");
		goto err;
	}

	row_buffer = calloc(height, row_bytes);
	if (!row_buffer) {
		LOG("cannot allocate row_buffer");
		goto err;
	}

	for (uint32_t y = 0; y < height; y++) {
		rows[y] = row_buffer + y * row_bytes;
	}

	png_read_image(png, rows);

	compressor->image_width = width;
	compressor->image_height = height;
	compressor->input_components = 3;
	compressor->in_color_space = JCS_RGB;

	jpeg_set_defaults(compressor);

	jpeg_start_compress(compressor, TRUE);

	for (uint32_t y = 0; y < height; y++) {
		JDIMENSION num_written = jpeg_write_scanlines(
				compressor, rows + y, 1);
		if (num_written != 1) {
			LOG("write only %u of 1 scanlines", num_written);
			break;
		}
	}

	okay = compressor->next_scanline >= compressor->image_height;

	jpeg_finish_compress(compressor);

err:
	free(rows);
	free(row_buffer);

	return okay;
}

static bool resize_png(
	const void *image, size_t image_size,
	size_t new_width,
	const char *output_path)
{
	bool okay = false;

	png_structp png = NULL;
	png_infop info = NULL;

	FILE *output = NULL;

	struct jpeg_compress_struct compressor;
	memset(&compressor, 0, sizeof(compressor));

	struct jpeg_error_mgr error_manager;
	memset(&error_manager, 0, sizeof(error_manager));

	jpeg_std_error(&error_manager);

	png = png_create_read_struct(PNG_LIBPNG_VER_STRING, NULL, NULL, NULL);
	if (!png) {
		LOG("cannot create read struct");
		goto err;
	}

	info = png_create_info_struct(png);
	if (!info) {
		LOG("cannot create info struct from read struct");
		goto err;
	}

	struct memory_view view = {
		.data = image,
		.offset = 0,
		.size = image_size,
	};
	png_set_read_fn(png, (void *)&view, png_read);

	// This setting ensures that we display images with incorrect
	// CMF bytes.  See crbug.com/807324.
	png_set_option(png, PNG_MAXIMUM_INFLATE_WINDOW, PNG_OPTION_ON);

	output = fopen(output_path, "wb");
	if (!output) {
		LOG("cannot open \"%s\": %s", output_path, strerror(errno));
		goto err;
	}

	compressor.err = &error_manager;

	jpeg_create_compress(&compressor);

	jpeg_stdio_dest(&compressor, output);

	LOG("ignore new_width (%zu) for now", new_width);
	okay = resize_png_impl(png, info, &compressor);

err:
	jpeg_destroy_compress(&compressor);

	if (output && fclose(output)) {
		LOG("cannot close \"%s\": %s", output_path, strerror(errno));
		okay = false;
	}

	if (png) {
		png_destroy_read_struct(&png, info ? &info : NULL, NULL);
	}

	return okay;
}

int main(int argc, char *argv[])
{
	return run_resize(argc, argv, resize_png);
}
