//
// Extension module for accessing native image libraries.
//

#include <assert.h>
#include <errno.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <jpeglib.h>


#ifdef __GNUC__
#define UNUSED __attribute__((__unused__))
#else
#define UNUSED
#endif


#define container_of(ptr, type, member) \
	((type *)((void *)(ptr)) - offsetof(type, member))


//
// Error handling.
//


static PyObject *ERROR_TYPE;


#define ERR(...) PyErr_Format(ERROR_TYPE, __VA_ARGS__)


struct error_manager {
	struct jpeg_error_mgr jpeg_error_manager;
	jmp_buf setjmp_buffer;
};


static void error_exit(j_common_ptr common_info)
{
	struct error_manager *error_manager = container_of(
		common_info->err,
		struct error_manager,
		jpeg_error_manager
	);

	common_info->err->output_message(common_info);

	longjmp(error_manager->setjmp_buffer, 1);
}


static void output_message(j_common_ptr common_info)
{
	char message[JMSG_LENGTH_MAX];
	common_info->err->format_message(common_info, message);

	ERR("libjpeg err: %s", message);
}


//
// Main module functions.
//


enum image_format {
	FORMAT_UNKNOWN = 0,
	FORMAT_GIF,
	FORMAT_JPEG,
	FORMAT_PNG,
};


static enum image_format detect_format(const void *image, size_t size)
{
	// Guard against strange input.
	if (size < 8) {
		return FORMAT_UNKNOWN;
	}

	if (!memcmp(image, "GIF87a", 6) || !memcmp(image, "GIF89a", 6)) {
		return FORMAT_GIF;
	} else if (!memcmp(image, "\xFF\xD8\xFF", 3)) {
		return FORMAT_JPEG;
	} else if (!memcmp(image, "\x89PNG\r\n\x1A\n", 8)) {
		return FORMAT_PNG;
	} else {
		return FORMAT_UNKNOWN;
	}
}


static void resize_jpeg_impl(
	const void *image, size_t size,
	int desired_width,
	const char *output_path,
	int *output_width, int *output_height,
	// "Local" variables that should not be clobbered by longjmp.
	bool *okay,
	struct jpeg_decompress_struct *decompressor,
	struct jpeg_compress_struct *compressor,
	struct error_manager *error_manager,
	FILE **output
)
{
	// First, establish setjmp return context.

	if (setjmp(error_manager->setjmp_buffer)) {
		return;
	}

	// Initialize decompressor.

	decompressor->err = &error_manager->jpeg_error_manager;

	jpeg_create_decompress(decompressor);

	jpeg_mem_src(decompressor, (unsigned char *)image, size);

	if (jpeg_read_header(decompressor, TRUE) != JPEG_HEADER_OK) {
		ERR("invalid jpeg header");
		return;
	}

	decompressor->scale_num = desired_width;
	decompressor->scale_denom = decompressor->image_width;

	if (!jpeg_start_decompress(decompressor)) {
		ERR("cannot start decompress");
		return;
	}

	if (output_width) {
		*output_width = decompressor->output_width;
	}
	if (output_height) {
		*output_height = decompressor->output_height;
	}

	// Initialize output.

	*output = fopen(output_path, "w");
	if (*output == NULL) {
		ERR("cannot open \"%s\": %s", output_path, strerror(errno));
		return;
	}

	// Initialize compressor.

	compressor->err = &error_manager->jpeg_error_manager;

	jpeg_create_compress(compressor);

	jpeg_stdio_dest(compressor, *output);

	compressor->image_width = decompressor->output_width;
	compressor->image_height = decompressor->output_height;
	compressor->input_components = decompressor->out_color_components;
	compressor->in_color_space = decompressor->out_color_space;

	jpeg_set_defaults(compressor);

	jpeg_start_compress(compressor, TRUE);

	// Start processing.

	int row_stride =
		decompressor->output_width * decompressor->output_components;

	JSAMPARRAY buffer = decompressor->mem->alloc_sarray(
		(j_common_ptr)decompressor, JPOOL_IMAGE, row_stride, 1);

	while (decompressor->output_scanline < decompressor->output_height) {

		JDIMENSION num_read = jpeg_read_scanlines(
			decompressor, buffer, 1);

		JDIMENSION num_write = jpeg_write_scanlines(
			compressor, buffer, num_read);

		if (num_read != num_write) {
			ERR("write %u of %u scanlines", num_write, num_read);
			break;
		}
	}

	*okay = compressor->next_scanline >= compressor->image_height;

	// Clean up and return.

	jpeg_finish_compress(compressor);

	if (!jpeg_finish_decompress(decompressor)) {
		ERR("cannot finish decompressor");
		*okay = false;
	}
}


static bool resize_jpeg(
	const void *image, size_t size,
	int desired_width,
	const char *output_path,
	int *output_width, int *output_height
)
{
	bool okay = false;

	FILE *output = NULL;

	struct jpeg_compress_struct compressor;
	memset(&compressor, 0, sizeof(compressor));

	struct jpeg_decompress_struct decompressor;
	memset(&decompressor, 0, sizeof(decompressor));

	struct error_manager error_manager;
	memset(&error_manager, 0, sizeof(error_manager));

	jpeg_std_error(&error_manager.jpeg_error_manager);

	error_manager.jpeg_error_manager.error_exit = error_exit;
	error_manager.jpeg_error_manager.output_message = output_message;

	resize_jpeg_impl(
		image, size,
		desired_width,
		output_path,
		output_width, output_height,
		&okay,
		&decompressor,
		&compressor,
		&error_manager,
		&output
	);

	jpeg_destroy_decompress(&decompressor);

	jpeg_destroy_compress(&compressor);

	if (output && fclose(output)) {
		ERR("cannot close \"%s\": %s", output_path, strerror(errno));
		okay = false;
	}

	return okay;
}


//
// Python function definitions.
//


static PyObject *py_detect_format(PyObject* self UNUSED, PyObject *image)
{
	char *data = NULL;
	Py_ssize_t size = 0;

	if (PyBytes_AsStringAndSize(image, &data, &size) < 0) {
		return NULL;
	}

	assert(data && size >= 0);

	return PyLong_FromLong(detect_format(data, size));
}


static PyObject *py_resize_jpeg(PyObject* self UNUSED, PyObject *args)
{
	PyObject *ret = NULL;

	Py_buffer buffer;
	memset(&buffer, 0, sizeof(buffer));

	int desired_width = 0;

	PyObject *output_path = NULL;
	const char *output_path_cstr = NULL;

	if (!PyArg_ParseTuple(
		args, "y*iO&:resize",
		&buffer,
		&desired_width,
		PyUnicode_FSConverter, (void*)&output_path
	)) {
		return NULL;
	}

	assert(buffer.len >= 0);

	if (desired_width <= 0) {
		ERR("expect positive width: %d", desired_width);
		goto err;
	}

	output_path_cstr = PyBytes_AsString(output_path);
	if (!output_path_cstr) {
		goto err;
	}

	int output_width = 0;
	int output_height = 0;
	if (!resize_jpeg(
		buffer.buf, buffer.len,
		desired_width,
		output_path_cstr,
		&output_width, &output_height
	)) {
		goto err;
	}

	ret = Py_BuildValue("(ii)", output_width, output_height);

err:
	Py_XDECREF(output_path);

	PyBuffer_Release(&buffer);

	return ret;
}


//
// Module definition.
//


#define DEF_METHOD(name, flags) {					\
	.ml_name = #name, 						\
	.ml_meth = (PyCFunction)py_ ## name,				\
	.ml_flags = flags, 						\
	.ml_doc = NULL, 						\
}


static PyMethodDef METHOD_DEFS[] = {
	DEF_METHOD(detect_format, METH_O),
	DEF_METHOD(resize_jpeg, METH_VARARGS),
	{NULL, NULL, 0, NULL},
};


#undef DEF_METHOD


static struct PyModuleDef MODULE_DEF = {
	.m_base = PyModuleDef_HEAD_INIT,
	.m_name = "_imagetools",
	.m_doc = NULL,
	.m_size = -1,
	.m_methods = METHOD_DEFS,
	.m_slots = NULL,
	.m_traverse = NULL,
	.m_clear = NULL,
	.m_free = NULL,
};


PyMODINIT_FUNC PyInit__imagetools(void)
{
	PyObject *module = PyModule_Create(&MODULE_DEF);
	if (!module) {
		goto err;
	}

	ERROR_TYPE = PyErr_NewException("imagetools.ImageError", NULL, NULL);
	if (!ERROR_TYPE) {
		goto err;
	}

	if (PyModule_AddObject(module, "ImageError", ERROR_TYPE) < 0) {
		goto err;
	}

#define DEF_INT_CONST(x)						\
	if (PyModule_AddIntMacro(module, x) < 0) {			\
		goto err;						\
	}

	DEF_INT_CONST(FORMAT_UNKNOWN);
	DEF_INT_CONST(FORMAT_GIF);
	DEF_INT_CONST(FORMAT_JPEG);
	DEF_INT_CONST(FORMAT_PNG);

#undef DEF_INT_CONST

	return module;

err:
	ERROR_TYPE = NULL;

	if (module) {
		Py_DECREF(module);
	}

	return NULL;
}
