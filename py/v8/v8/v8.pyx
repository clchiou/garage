import logging
import os.path
from collections import Mapping, OrderedDict

from cython.operator cimport dereference as deref
from libc.stdint cimport uint32_t
from libcpp cimport bool


LOG = logging.getLogger(__name__)


### V8 ###


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


cdef extern from 'array_buffer_allocator.h' \
        namespace 'v8_python::ArrayBufferAllocator':
    cdef ArrayBuffer.Allocator* GetStatic()


cdef class Isolate:

    cdef _Isolate* isolate

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


cdef extern from 'handle_scope.h' namespace 'v8_python':

    cdef cppclass HandleScope:

        HandleScope(_Isolate* isolate)


cdef extern from 'object_helper.h' namespace 'v8_python':

    cdef bool ObjectHas (
        Local[_Context] context,
        Local[Object] object_,
        Local[String] name,
        bool* out)


# TODO: Make Context a MutableMapping
cdef class ContextBase:

    cdef _Isolate* isolate

    cdef HandleScope* handle_scope

    cdef Local[_Context] context

    cdef Local[Object] global_vars

    cdef Local[String] _encode_string(self, string)

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

        return js2py(self.context, value_object)

    def __contains__(self, name):
        assert self.handle_scope is not NULL
        cdef Local[String] name_object = self._encode_string(name)
        cdef bool has
        cdef bool okay = ObjectHas(
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
        return js2py(self.context, value)

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
            yield js2py(self.context, name)

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


### Helper functions ###


# Cython can only stack allocate C++ objects with default constructors :(
cdef js2py(Local[_Context] context, Local[Value] value):
    cdef Local[Array] array
    cdef Local[Object] obj
    cdef Local[Value] tmp
    cdef MaybeLocal[Array] maybe_array
    cdef MaybeLocal[Value] maybe_value
    cdef uint32_t i

    if deref(value).IsNull():
        return None

    elif deref(value).IsTrue():
        return True

    elif deref(value).IsFalse():
        return False

    elif deref(value).IsArray():
        array = ToArray(value)
        output = []
        for i in range(deref(array).Length()):
            maybe_value = deref(array).Get(context, i)
            if not maybe_value.ToLocal(&tmp):
                raise RuntimeError('cannot get array element %d' % i)
            output.append(js2py(context, tmp))
        return output

    elif deref(value).IsMap():
        # Cython doesn't support closure (so no list comprehension).
        array = deref(ToMap(value)).AsArray()
        omap = OrderedDict()
        for i in range(0, deref(array).Length(), 2):

            maybe_value = deref(array).Get(context, i)
            if not maybe_value.ToLocal(&tmp):
                raise RuntimeError('cannot get %d-th map key' % (i / 2))
            key = js2py(context, tmp)

            maybe_value = deref(array).Get(context, i + 1)
            if not maybe_value.ToLocal(&tmp):
                raise RuntimeError('cannot get %d-th map value' % (i / 2))
            omap[key] = js2py(context, tmp)

        return omap

    elif deref(value).IsString():
        return value_as_str(value)

    elif deref(value).IsNumber():
        if deref(value).IsInt32() or deref(value).IsUint32():
            return deref(ToInteger(value)).Value()
        else:
            return deref(ToNumber(value)).Value()

    elif is_just_object(value):
        obj = ToObject(value)
        maybe_array = deref(obj).GetPropertyNames(context)
        if not maybe_array.ToLocal(&array):
            raise RuntimeError('cannot get property names of an object')
        data = {}
        for i in range(deref(array).Length()):

            maybe_value = deref(array).Get(context, i)
            if not maybe_value.ToLocal(&tmp):
                raise RuntimeError('cannot get %d-th object key' % i)
            key = js2py(context, tmp)

            maybe_value = deref(obj).Get(context, tmp)
            if not maybe_value.ToLocal(&tmp):
                raise RuntimeError('cannot get %d-th object value' % i)
            data[key] = js2py(context, tmp)

        return data

    else:
        return JavaScript(value_as_str(value))


cdef is_just_object(Local[Value] value):
    # TODO: This is brittle. Fix this!
    return deref(value).IsObject() and not (
        deref(value).IsArray() or
        deref(value).IsArrayBuffer() or
        deref(value).IsArrayBufferView() or
        deref(value).IsSharedArrayBuffer() or
        deref(value).IsDate() or
        deref(value).IsFunction() or
        deref(value).IsMap() or
        deref(value).IsPromise() or
        deref(value).IsRegExp() or
        deref(value).IsSet() or
        deref(value).IsString() or
        deref(value).IsBooleanObject() or
        deref(value).IsNumberObject() or
        deref(value).IsStringObject() or
        deref(value).IsSymbolObject()
    )


cdef value_as_str(Local[Value] value):
    cdef String.Utf8Value* utf8 = new String.Utf8Value(value)
    cdef const char* cstr
    cdef bytes byte_string
    try:
        cstr = deref(deref(utf8))
        if cstr is NULL:
            raise RuntimeError('cannot translate JavaScript value into string')
        byte_string = <bytes> cstr
        return byte_string.decode('utf-8')
    finally:
        del utf8


class JavaScript:
    """A JavaScript object that cannot be translated into a Python object."""

    def __init__(self, js_repr):
        self.js_repr = js_repr

    def __str__(self):
        return 'JavaScript([%s])' % self.js_repr

    def __repr__(self):
        return 'JavaScript([%s])' % self.js_repr
