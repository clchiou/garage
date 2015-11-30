#ifndef V8CABI_H_
#define V8CABI_H_

#ifdef __cplusplus
#  include <cstdint>
#else
#  include <stdint.h>
#endif

#ifdef __cplusplus
extern "C" {
#endif

// C99's bool and C++'s bool might not be binary compatible.
typedef uint8_t BOOL;

// V8 object wrappers.
struct context;
struct handle_scope;
struct isolate;
struct isolate_create_params;
struct platform;

// JavaScript values.
struct script;
struct string;
struct utf8_value;
struct value;

// v8::Context

struct context *v8_context_new(struct isolate *isolate);
void v8_context_enter(struct context *context);
void v8_context_exit(struct context *context);
void v8_context_delete(struct context *context);

// v8::HandleScope

struct handle_scope *v8_handle_scope_new(struct isolate *isolate);
void v8_handle_scope_delete(struct handle_scope *handle_scope);

// v8::Isolate

struct isolate *v8_isolate_new(struct isolate_create_params *params);
void v8_isolate_enter(struct isolate *isolate);
void v8_isolate_exit(struct isolate *isolate);
void v8_isolate_dispose(struct isolate *isolate);

// v8::Isolate::CreateParams

struct isolate_create_params *v8_isolate_create_params_new(void);
void v8_isolate_create_params_delete(struct isolate_create_params *params);

// v8::V8

BOOL v8_initialize(void);
BOOL v8_initialize_icu(const char *icu_data_file);
void v8_initialize_external_startup_data(const char *directory_path);
void v8_initialize_external_startup_data2(
		const char *natives_blob, const char *snapshot_blob);
void v8_initialize_platform(struct platform *platform);
BOOL v8_dispose(void);
void v8_shutdown_platform(void);

// v8::platform

struct platform *v8_platform_create_default_platform(int thread_pool_size);
void v8_platform_delete(struct platform *platform);

// JavaScript values.

// v8::Script

struct script *v8_script_compile(
		struct context *context, struct string *source);
void v8_script_delete(struct script *script);

// v8::String

struct string *v8_string_new_from_utf8(
	struct isolate *isolate, const char *data);
struct value *v8_script_run(struct script *script, struct context *context);
void v8_string_delete(struct string *string);

// v8::String::Utf8Value

struct utf8_value *v8_utf8_value_new(struct value *value);
const char *v8_utf8_value_cstr(struct utf8_value *utf8_value);
void v8_utf8_value_delete(struct utf8_value *utf8_value);

// v8::Value

void v8_value_delete(struct value *value);

#ifdef __cplusplus
}
#endif

#endif  // V8CABI_H_
