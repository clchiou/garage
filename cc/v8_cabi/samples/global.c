#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "v8_cabi.h"

#define USAGE "Usage: %s /path/to/native/blob /and/snapshot/blob\n"

struct value *eval(
		struct isolate *isolate,
		struct context *context,
		const char *source_string);

const char *value_to_cstr(struct value *value, char *output, size_t size);

int main(int argc, char *argv[])
{
	if (argc < 3) {
		printf(USAGE, argv[0]);
		return 1;
	}

	v8_initialize_icu(NULL);
	v8_initialize_external_startup_data2(argv[1], argv[2]);
	struct platform *platform = v8_platform_create_default_platform(0);
	v8_initialize_platform(platform);
	v8_initialize();

	struct isolate_create_params *create_params =
		v8_isolate_create_params_new();
	struct isolate *isolate = v8_isolate_new(create_params);

	v8_isolate_enter(isolate);

	struct handle_scope *handle_scope = v8_handle_scope_new(isolate);

	struct context *context = v8_context_new(isolate);

	v8_context_enter(context);

	// Execute code.

	char source[64];
	char buffer[64];
	struct value *value;

	snprintf(source, sizeof(source), "x = \"spam\";");
	value = eval(isolate, context, source);
	fprintf(stdout, "> %s\n%s\n",
		source, value_to_cstr(value, buffer, sizeof(buffer)));
	v8_value_delete(value);

	snprintf(source, sizeof(source), "y = \"egg\";");
	value = eval(isolate, context, source);
	fprintf(stdout, "> %s\n%s\n",
		source, value_to_cstr(value, buffer, sizeof(buffer)));
	v8_value_delete(value);

	snprintf(source, sizeof(source), "z = 3.14159;");
	value = eval(isolate, context, source);
	fprintf(stdout, "> %s\n%s\n",
		source, value_to_cstr(value, buffer, sizeof(buffer)));
	v8_value_delete(value);

	struct object *global = v8_context_global(context);
	struct array *names = v8_object_get_property_names(global, context);

	fprintf(stdout, "---\n");

	uint32_t length = v8_array_length(names);
	for (uint32_t i = 0; i < length; i++) {
		struct value *name = v8_array_get(names, context, i);
		value = v8_object_get(global, context, name);

		const char *type;
		if (v8_value_is_string(value)) {
			type = "type string";
		} else {
			type = "something else";
		}

		fprintf(stdout, "%s is %s of %s\n",
			value_to_cstr(name, source, sizeof(source)),
			value_to_cstr(value, buffer, sizeof(buffer)),
			type);

		v8_value_delete(value);
		v8_value_delete(name);
	}

	v8_array_delete(names);
	v8_object_delete(global);

	// Exit.

	v8_context_exit(context);
	v8_context_delete(context);

	v8_handle_scope_delete(handle_scope);

	v8_isolate_exit(isolate);

	v8_isolate_dispose(isolate);
	v8_isolate_create_params_delete(create_params);
	v8_dispose();
	v8_shutdown_platform();
	v8_platform_delete(platform);

	return 0;
}

struct value *eval(
		struct isolate *isolate,
		struct context *context,
		const char *source_string)
{
	struct string *source =
		v8_string_new_from_utf8(isolate, source_string);
	assert(source);

	struct script *script = v8_script_compile(context, source);
	assert(script);

	struct value *value = v8_script_run(script, context);
	assert(value);

	v8_script_delete(script);
	v8_string_delete(source);

	return value;
}

const char *value_to_cstr(struct value *value, char *output, size_t size)
{
	struct utf8_value *utf8 = v8_utf8_value_new(value);
	assert(utf8);
	strncpy(output, v8_utf8_value_cstr(utf8), size);
	output[size - 1] = '\0';
	v8_utf8_value_delete(utf8);
	return output;
}
