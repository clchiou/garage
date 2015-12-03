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
struct array;
struct map;
struct object;
struct script;
struct string;
struct utf8_value;
struct value;

// v8::Context

struct context *v8_context_new(struct isolate *isolate);
void v8_context_enter(struct context *context);
struct object *v8_context_global(struct context *context);
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

// v8::Array

struct array *v8_array_cast_from(struct value *value);
uint32_t v8_array_length(struct array *array);
struct value *v8_array_get(
		struct array *array, struct context *context, uint32_t index);
void v8_array_delete(struct array *array);

// v8::Map

struct map *v8_map_cast_from(struct value *value);
struct array *v8_map_as_array(struct map *map);
void v8_map_delete(struct map *map);

// v8::Number

double v8_number_cast_from(struct value *value);

// v8::Object

struct array *v8_object_get_property_names(
		struct object *object, struct context *context);
BOOL v8_object_has(
		struct object *object,
		struct context *context,
		struct value *key,
		BOOL *has);
struct value *v8_object_get(
		struct object *object,
		struct context *context,
		struct value *key);
BOOL v8_object_set(
		struct object *object,
		struct context *context,
		struct value *key,
		struct value *value,
		BOOL *set);
BOOL v8_object_del(
		struct object *object,
		struct context *context,
		struct value *key,
		BOOL *del);
void v8_object_delete(struct object *object);

// v8::Script

struct script *v8_script_compile(
		struct context *context, struct string *source);
struct value *v8_script_run(struct script *script, struct context *context);
void v8_script_delete(struct script *script);

// v8::String

struct string *v8_string_new_from_utf8(
	struct isolate *isolate, const char *data);
void v8_string_delete(struct string *string);

// v8::String::Utf8Value

struct utf8_value *v8_utf8_value_new(struct value *value);
const char *v8_utf8_value_cstr(struct utf8_value *utf8_value);
void v8_utf8_value_delete(struct utf8_value *utf8_value);

// v8::Value

BOOL v8_value_is_array(struct value *value);
BOOL v8_value_is_map(struct value *value);
BOOL v8_value_is_object(struct value *value);
BOOL v8_value_is_string(struct value *value);

BOOL v8_value_is_number(struct value *value);
BOOL v8_value_is_int32(struct value *value);
BOOL v8_value_is_uint32(struct value *value);

void v8_value_delete(struct value *value);

#ifdef __cplusplus
}
#endif

#endif  // V8CABI_H_
