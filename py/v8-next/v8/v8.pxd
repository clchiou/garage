from libc.stdint cimport int64_t, uint32_t
from libcpp cimport bool


cdef extern from 'include/v8.h' namespace 'v8':

    ### Templates ###

    cdef cppclass Local[T]:

        bool IsEmpty() const

        void Clear()

        T* operator*()

    cdef cppclass MaybeLocal[T]:
        # TODO: Should be Local[S].
        bool ToLocal(Local[T]* out) const

    ### JavaScript Objects ###

    # Hack for template function with multiple variables.
    Local[Value] Local_Cast 'v8::Local<v8::Value>::Cast'(Local[String] that)
    Local[Array] ToArray 'v8::Local<v8::Array>::Cast'(Local[Value] that)
    Local[Integer] ToInteger 'v8::Local<v8::Integer>::Cast'(Local[Value] that)
    Local[Map] ToMap 'v8::Local<v8::Map>::Cast'(Local[Value] that)
    Local[Number] ToNumber 'v8::Local<v8::Number>::Cast'(Local[Value] that)
    Local[Object] ToObject 'v8::Local<v8::Object>::Cast'(Local[Value] that)

    cdef cppclass Object:
        MaybeLocal[Array] GetPropertyNames(Local[_Context] context)
        MaybeLocal[Value] Get(Local[_Context] context, Local[Value] key)
        MaybeLocal[Value] Get(Local[_Context] context, uint32_t index)

    cdef cppclass Array(Object):
        uint32_t Length() const

    cdef cppclass Integer:
        int64_t Value()

    cdef cppclass Map:
        Local[Array] AsArray() const

    cdef cppclass Number:
        double Value()

    cdef cppclass Script:
        MaybeLocal[Value] Run(Local[_Context] context)

    MaybeLocal[Script] Script_Compile 'v8::Script::Compile'(
        Local[_Context] context, Local[String] source)

    cdef cppclass String:
        cppclass Utf8Value:
            Utf8Value(Local[Value] obj)
            const char* operator*() const

    cdef enum NewStringType:
        kNormal 'v8::NewStringType::kNormal',
        kInternalized 'v8::NewStringType::kInternalized'

    MaybeLocal[String] String_NewFromUtf8 'v8::String::NewFromUtf8'(
        _Isolate* isolate, const char* data, NewStringType type)

    cdef cppclass Value:
        bool IsUndefined()
        bool IsNull()
        bool IsTrue()
        bool IsFalse()
        # Subclasses of Object.
        bool IsObject()
        bool IsArray()
        bool IsArrayBuffer()
        bool IsArrayBufferView()
        bool IsSharedArrayBuffer()
        bool IsDate()
        bool IsFunction()
        bool IsMap()
        bool IsPromise()
        bool IsRegExp()
        bool IsSet()
        bool IsString()
        bool IsBooleanObject()
        bool IsNumberObject()
        bool IsStringObject()
        bool IsSymbolObject()
        # Numeric classes.
        bool IsNumber()
        bool IsInt32()
        bool IsUint32()

    ### V8 Objects ###

    cdef cppclass ArrayBuffer:

        cppclass Allocator

    cdef cppclass _Isolate 'v8::Isolate':

        cppclass CreateParams:
            CreateParams()
            ArrayBuffer.Allocator* array_buffer_allocator

        void Enter()

        void Exit()

        void Dispose()

    _Isolate* Isolate_New 'v8::Isolate::New'(
        const _Isolate.CreateParams& params)

    cdef cppclass _Context 'v8::Context':

        Local[Object] Global()

        void Enter()

        void Exit()

    Local[_Context] Context_New 'v8::Context::New'(_Isolate* isolate)


cdef extern from 'handle_scope.cpp' namespace 'v8_python':

    cdef cppclass HandleScope:

        HandleScope(_Isolate* isolate)


cdef class Isolate:

    cdef _Isolate* isolate


cdef class ContextBase:

    cdef _Isolate* isolate

    cdef HandleScope* handle_scope

    cdef Local[_Context] context

    cdef Local[Object] global_vars

    cdef Local[String] _encode_string(self, string)
