import logging
import os.path
from collections import Mapping

from cython.operator cimport dereference as deref
from libc.stdint cimport uint32_t
from libcpp cimport bool

cimport translate


LOG = logging.getLogger(__name__)


### V8 ###


cdef extern from 'include/v8.h' namespace 'v8':

    cdef cppclass Platform


# Hack for static methods of v8::V8.
cdef extern from 'include/v8.h' namespace 'v8::V8':

    cdef bool Initialize()

    cdef bool InitializeICU(const char* icu_data_file)

    cdef void InitializeExternalStartupData(
        const char* natives_blob, const char* snapshot_blob)

    cdef void InitializePlatform(Platform* platform)

    cdef bool Dispose()

    cdef void ShutdownPlatform()


cdef extern from 'include/libplatform/libplatform.h' namespace 'v8::platform':

    Platform* CreateDefaultPlatform(int thread_pool_size)


cdef class V8:

    cdef str natives_blob_path
    cdef str snapshot_blob_path

    cdef Platform* platform

    def __init__(self, natives_blob_path=None, snapshot_blob_path=None):
        here = os.path.dirname(__file__)
        self.natives_blob_path = (
            natives_blob_path or os.path.join(here, 'data/natives_blob.bin'))
        self.snapshot_blob_path = (
            snapshot_blob_path or os.path.join(here, 'data/snapshot_blob.bin'))
        self.platform = NULL

    def __enter__(self):
        assert self.platform is NULL
        LOG.info('initialize V8')

        if not InitializeICU(NULL):
            raise RuntimeError('cannot initialize ICU')

        for path in (self.natives_blob_path, self.snapshot_blob_path):
            if not os.path.exists(path):
                raise RuntimeError('%r does not exist' % path)
        natives_blob_path_bytes = self.natives_blob_path.encode('utf-8')
        snapshot_blob_path_bytes = self.snapshot_blob_path.encode('utf-8')
        cdef char* natives_blob_path_cstr = natives_blob_path_bytes
        cdef char* snapshot_blob_path_cstr = snapshot_blob_path_bytes
        InitializeExternalStartupData(
            natives_blob_path_cstr,
            snapshot_blob_path_cstr,
        )

        self.platform = CreateDefaultPlatform(0)
        if self.platform is NULL:
            raise RuntimeError('cannot initialize platform object')
        InitializePlatform(self.platform)

        if not Initialize():
            del self.platform
            self.platform = NULL
            raise RuntimeError('cannot initialize V8')

        return self

    def __exit__(self, *_):
        assert self.platform is not NULL
        LOG.info('tear down V8')

        if not Dispose():
            raise RuntimeError('cannot dispose V8')

        ShutdownPlatform()

        del self.platform
        self.platform = NULL

    def isolate(self):
        assert self.platform is not NULL
        return Isolate()


### Isolate ###


cdef extern from 'array_buffer_allocator.cpp' \
        namespace 'v8_python::ArrayBufferAllocator':
    cdef ArrayBuffer.Allocator* GetStatic()


cdef class Isolate:

    def __init__(self):
        self.isolate = NULL

    def __enter__(self):
        assert self.isolate is NULL

        LOG.info('create isolate')
        cdef _Isolate.CreateParams params
        params.array_buffer_allocator = GetStatic()
        self.isolate = Isolate_New(params)
        if self.isolate is NULL:
            raise RuntimeError('cannot initialize isolate')

        LOG.info('enter isolate')
        self.isolate.Enter()

        return self

    def __exit__(self, *_):
        assert self.isolate is not NULL

        LOG.info('exit isolate')
        self.isolate.Exit()

        LOG.info('dispose isolate')
        self.isolate.Dispose()
        self.isolate = NULL

    def context(self):
        return Context(self)


### Context ###


cdef extern from 'object_helper.cpp' namespace 'v8_python':

    cdef bool ObjectHelper_Has 'v8_python::ObjectHelper::Has'(
        Local[_Context] context,
        Local[Object] object_,
        Local[String] name,
        bool* out)


# TODO: Make Context a MutableMapping
cdef class ContextBase:

    def __init__(self, Isolate isolate):
        assert isolate.isolate is not NULL
        self.isolate = isolate.isolate
        self.handle_scope = NULL

    def __enter__(self):
        assert self.handle_scope is NULL

        self.handle_scope = new HandleScope(self.isolate)
        if self.handle_scope is NULL:
            raise RuntimeError('cannot initialize handle scope')

        self.context = Context_New(self.isolate)
        if self.context.IsEmpty():
            del self.handle_scope
            self.handle_scope = NULL
            raise RuntimeError('cannot initialize context')

        deref(self.context).Enter()

        self.global_vars = deref(self.context).Global()

        return self

    def __exit__(self, *_):
        assert self.handle_scope is not NULL

        deref(self.context).Exit()

        del self.handle_scope
        self.handle_scope = NULL

    def execute(self, source):
        assert self.handle_scope is not NULL

        cdef Local[String] source_object = self._encode_string(source)

        cdef MaybeLocal[Script] maybe_script = Script_Compile(
            self.context, source_object)
        cdef Local[Script] script_object
        if not maybe_script.ToLocal(&script_object):
            raise RuntimeError('cannot compile source %r' % source)

        cdef MaybeLocal[Value] maybe_value = deref(script_object).Run(
            self.context)
        cdef Local[Value] value_object
        if not maybe_value.ToLocal(&value_object):
            raise RuntimeError('cannot execute source %r' % source)

        return translate.js2py(self.context, value_object)

    def __contains__(self, name):
        assert self.handle_scope is not NULL
        cdef Local[String] name_object = self._encode_string(name)
        cdef bool has
        cdef bool okay = ObjectHelper_Has(
            self.context, self.global_vars, name_object, &has)
        if not okay:
            raise RuntimeError(
                'error when calling v8::Object::Has for %r' % name)
        return has

    def __getitem__(self, name):
        assert self.handle_scope is not NULL
        cdef Local[Value] value
        cdef MaybeLocal[Value] maybe_value = deref(self.global_vars).Get(
            self.context, Local_Cast(self._encode_string(name)))
        if not maybe_value.ToLocal(&value):
            raise RuntimeError('cannot get global variable name %r' % name)
        if deref(value).IsUndefined():
            raise KeyError(name)
        return translate.js2py(self.context, value)

    def __len__(self):
        assert self.handle_scope is not NULL
        cdef Local[Array] array
        cdef MaybeLocal[Array] maybe_array
        maybe_array = deref(self.global_vars).GetPropertyNames(self.context)
        if not maybe_array.ToLocal(&array):
            raise RuntimeError('cannot get global variable names')
        return deref(array).Length()

    def __iter__(self):
        assert self.handle_scope is not NULL
        cdef Local[Array] array
        cdef Local[Value] name
        cdef MaybeLocal[Array] maybe_array
        cdef MaybeLocal[Value] maybe_name
        cdef uint32_t i
        maybe_array = deref(self.global_vars).GetPropertyNames(self.context)
        if not maybe_array.ToLocal(&array):
            raise RuntimeError('cannot get global variable names')
        for i in range(deref(array).Length()):
            maybe_name = deref(array).Get(self.context, i)
            if not maybe_name.ToLocal(&name):
                raise RuntimeError('cannot get %d-th name of globals' % i)
            yield translate.js2py(self.context, name)

    cdef Local[String] _encode_string(self, string):
        if isinstance(string, bytes):
            string_bytes = string
        else:
            string_bytes = string.encode('utf-8')
        cdef char* string_cstr = string_bytes
        cdef MaybeLocal[String] maybe_string = String_NewFromUtf8(
            self.isolate, string_cstr, kNormal)
        cdef Local[String] string_object
        if not maybe_string.ToLocal(&string_object):
            raise RuntimeError('cannot encode string %r' % string)
        return string_object


class Context(ContextBase, Mapping):
    pass
