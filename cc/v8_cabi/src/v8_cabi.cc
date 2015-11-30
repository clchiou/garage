#include <cstdlib>
#include <cstring>

#include "include/libplatform/libplatform.h"
#include "include/v8.h"

#include "include/v8_cabi.h"

// Because v8::HandleScope forbids new/delete directly...
struct handle_scope {
	explicit handle_scope(struct isolate *isolate);
	v8::HandleScope handle_scope_;
};

// Whitelist of conversions between V8 type and its wrapper.
#define MAKE_CAST(S, T) \
	static inline T *cast(S *ptr) { return reinterpret_cast<T*>(ptr); } \
	static inline S *cast(T *ptr) { return reinterpret_cast<S*>(ptr); }
// V8 objects.
MAKE_CAST(struct context, v8::Local<v8::Context>)
MAKE_CAST(struct isolate, v8::Isolate)
MAKE_CAST(struct isolate_create_params, v8::Isolate::CreateParams)
MAKE_CAST(struct platform, v8::Platform)
// JavaScript values.
MAKE_CAST(struct array, v8::Local<v8::Array>)
MAKE_CAST(struct object, v8::Local<v8::Object>)
MAKE_CAST(struct script, v8::Local<v8::Script>)
MAKE_CAST(struct string, v8::Local<v8::String>)
MAKE_CAST(struct utf8_value, v8::String::Utf8Value)
MAKE_CAST(struct value, v8::Local<v8::Value>)
#undef MAKE_CAST

template <class T>
static inline v8::Local<T> *to_heap(v8::Local<T> v)
{
	return new v8::Local<T>(v);
}

template <class T>
static inline v8::Local<T> *unwrap(v8::MaybeLocal<T> v)
{
	if (v.IsEmpty()) {
		return nullptr;
	} else {
		return to_heap(v.ToLocalChecked());
	}
}

// v8::Context

struct context *v8_context_new(struct isolate *isolate)
{
	return cast(to_heap(v8::Context::New(cast(isolate))));
}

void v8_context_enter(struct context *context)
{
	(*cast(context))->Enter();
}

struct object *v8_context_global(struct context *context)
{
	return cast(to_heap((*cast(context))->Global()));
}

void v8_context_exit(struct context *context)
{
	(*cast(context))->Exit();
}

void v8_context_delete(struct context *context)
{
	delete cast(context);
}

// v8::HandleScope

handle_scope::handle_scope(struct isolate *isolate)
	: handle_scope_(cast(isolate))
{
}

struct handle_scope *v8_handle_scope_new(struct isolate *isolate)
{
	return new handle_scope(isolate);
}

void v8_handle_scope_delete(struct handle_scope *handle_scope)
{
	delete handle_scope;
}

// v8::Isolate

struct isolate *v8_isolate_new(struct isolate_create_params *params)
{
	return cast(v8::Isolate::New(*cast(params)));
}

void v8_isolate_enter(struct isolate *isolate)
{
	cast(isolate)->Enter();
}

void v8_isolate_exit(struct isolate *isolate)
{
	cast(isolate)->Exit();
}

void v8_isolate_dispose(struct isolate *isolate)
{
	cast(isolate)->Dispose();
}

// v8::Isolate::CreateParams

// Default array buffer allocator.
class ArrayBufferAllocator : public v8::ArrayBuffer::Allocator {
public:
	virtual void *Allocate(size_t length)
	{
		void *data = AllocateUninitialized(length);
		return !data ? data : memset(data, 0, length);
	}

	virtual void* AllocateUninitialized(size_t length)
	{
		return malloc(length);
	}

	virtual void Free(void* data, size_t)
	{
		free(data);
	}
};

struct isolate_create_params *v8_isolate_create_params_new(void)
{
	static ArrayBufferAllocator allocator;
	auto *params = new v8::Isolate::CreateParams;
	params->array_buffer_allocator = &allocator;
	return cast(params);
}

void v8_isolate_create_params_delete(struct isolate_create_params *params)
{
	delete cast(params);
}

// v8::V8

BOOL v8_initialize(void)
{
	return v8::V8::Initialize();
}

BOOL v8_initialize_icu(const char *icu_data_file)
{
	return v8::V8::InitializeICU(icu_data_file);
}

void v8_initialize_external_startup_data(const char *directory_path)
{
	v8::V8::InitializeExternalStartupData(directory_path);
}

void v8_initialize_external_startup_data2(
		const char *natives_blob, const char *snapshot_blob)
{
	v8::V8::InitializeExternalStartupData(natives_blob, snapshot_blob);
}

void v8_initialize_platform(struct platform *platform)
{
	v8::V8::InitializePlatform(cast(platform));
}

BOOL v8_dispose(void)
{
	return v8::V8::Dispose();
}

void v8_shutdown_platform(void)
{
	return v8::V8::ShutdownPlatform();
}

// v8::platform

struct platform *v8_platform_create_default_platform(int thread_pool_size)
{
	return cast(v8::platform::CreateDefaultPlatform(thread_pool_size));
}

void v8_platform_delete(struct platform *platform)
{
	delete cast(platform);
}

// JavaScript values.

// v8::Array

uint32_t v8_array_length(struct array *array)
{
	return (*cast(array))->Length();
}

struct value *v8_array_get(
		struct array *array, struct context *context, uint32_t index)
{
	return cast(unwrap((*cast(array))->Get(*cast(context), index)));
}

void v8_array_delete(struct array *array)
{
	delete cast(array);
}

// v8::Object

static inline BOOL unwrap(v8::Maybe<bool> maybe, BOOL *out)
{
	if (maybe.IsNothing()) {
		return false;
	}
	*out = maybe.FromJust();
	return true;
}

struct array *v8_object_get_property_names(
		struct object *object, struct context *context)
{
	return cast(unwrap((*cast(object))->GetPropertyNames(*cast(context))));
}

BOOL v8_object_has(
		struct object *object,
		struct context *context,
		struct value *key,
		BOOL *has)
{
	return unwrap((*cast(object))->Has(*cast(context), *cast(key)), has);
}

struct value *v8_object_get(
		struct object *object,
		struct context *context,
		struct value *key)
{
	return cast(unwrap((*cast(object))->Get(*cast(context), *cast(key))));
}

BOOL v8_object_set(
		struct object *object,
		struct context *context,
		struct value *key,
		struct value *value,
		BOOL *set)
{
	v8::Maybe<bool> maybe =
		(*cast(object))->Set(*cast(context), *cast(key), *cast(value));
	return unwrap(maybe, set);
}

BOOL v8_object_del(
		struct object *object,
		struct context *context,
		struct value *key,
		BOOL *del)
{
	return unwrap((*cast(object))->Has(*cast(context), *cast(key)), del);
}

void v8_object_delete(struct object *object)
{
	delete cast(object);
}

// v8::Script

struct script *v8_script_compile(
		struct context *context, struct string *source)
{
	auto *cxt = cast(context);
	auto *src = cast(source);
	return cast(unwrap(v8::Script::Compile(*cxt, *src)));
}

struct value *v8_script_run(struct script *script, struct context *context)
{
	return cast(unwrap((*cast(script))->Run(*cast(context))));
}

void v8_script_delete(struct script *script)
{
	delete cast(script);
}

// v8::String

struct string *v8_string_new_from_utf8(
		struct isolate *isolate, const char *data)
{
	return cast(unwrap(v8::String::NewFromUtf8(
		cast(isolate), data, v8::NewStringType::kNormal)));
}

void v8_string_delete(struct string *string) {
	delete cast(string);
}

// v8::String::Utf8Value

struct utf8_value *v8_utf8_value_new(struct value *value)
{
	auto *utf8 = new v8::String::Utf8Value(*cast(value));
	if (!**utf8) {
		delete utf8;
		return nullptr;
	} else {
		return cast(utf8);
	}
}

const char *v8_utf8_value_cstr(struct utf8_value *utf8_value)
{
	return **cast(utf8_value);
}

void v8_utf8_value_delete(struct utf8_value *utf8_value)
{
	delete cast(utf8_value);
}

// v8::Value

#define MAKE_IS_TYPE(S, T) \
	BOOL v8_value_is_##S(struct value *value) \
	{ return (*cast(value))->Is##T(); }
MAKE_IS_TYPE(array, Array)
MAKE_IS_TYPE(object, Object)
MAKE_IS_TYPE(string, String)
#undef MAKE_IS_TYPE

void v8_value_delete(struct value *value)
{
	delete cast(value);
}
