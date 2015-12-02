#include <assert.h>
#include <stdio.h>

#include "v8_cabi.h"

#define USAGE "Usage: %s /path/to/natives/blob /and/snapshot/blob\n"

#define SOURCE "'Hello' + ', World!'"

int main(int argc, char *argv[])
{
	if (argc < 3) {
		printf(USAGE, argv[0]);
		return 1;
	}

	fprintf(stderr, "Initialize V8\n");
	v8_initialize_icu(NULL);
	v8_initialize_external_startup_data2(argv[1], argv[2]);
	struct platform *platform = v8_platform_create_default_platform(0);
	v8_initialize_platform(platform);
	v8_initialize();

	fprintf(stderr, "Create a new isolate and make it the current one\n");
	struct isolate_create_params *create_params =
		v8_isolate_create_params_new();
	struct isolate *isolate = v8_isolate_new(create_params);

	fprintf(stderr, "Enter isolate\n");
	v8_isolate_enter(isolate);

	fprintf(stderr, "Create a stack-allocated handle scope\n");
	struct handle_scope *handle_scope = v8_handle_scope_new(isolate);

	fprintf(stderr, "Create a new context\n");
	struct context *context = v8_context_new(isolate);

	fprintf(stderr, "Enter context\n");
	v8_context_enter(context);

	fprintf(stderr, "Create JavaScript source code string\n");
	struct string *source = v8_string_new_from_utf8(isolate, SOURCE);
	assert(source);

	fprintf(stderr, "Compile the source code\n");
	struct script *script = v8_script_compile(context, source);
	assert(script);

	fprintf(stderr, "Run the script to get the result\n");
	struct value *result = v8_script_run(script, context);
	assert(result);

	struct utf8_value *utf8 = v8_utf8_value_new(result);
	assert(utf8);
	printf("Result: %s\n", v8_utf8_value_cstr(utf8));

	fprintf(stderr, "Delete objects\n");
	v8_utf8_value_delete(utf8);
	v8_value_delete(result);
	v8_script_delete(script);
	v8_string_delete(source);

	fprintf(stderr, "Exit and delete context\n");
	v8_context_exit(context);
	v8_context_delete(context);

	fprintf(stderr, "Delete handle scope\n");
	v8_handle_scope_delete(handle_scope);

	fprintf(stderr, "Exit isolate\n");
	v8_isolate_exit(isolate);

	fprintf(stderr, "Dispose the isolate and tear down V8\n");
	v8_isolate_dispose(isolate);
	v8_isolate_create_params_delete(create_params);
	v8_dispose();
	v8_shutdown_platform();
	v8_platform_delete(platform);

	return 0;
}
