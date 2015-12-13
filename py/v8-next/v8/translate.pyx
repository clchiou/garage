from collections import OrderedDict

from cython.operator cimport dereference as deref
from libc.stdint cimport uint32_t

from v8 cimport (
    Local,
    MaybeLocal,

    Local_Cast,
    ToArray,
    ToInteger,
    ToMap,
    ToNumber,
    ToObject,

    Array,
    Integer,
    Map,
    Number,
    Object,
    String,
)


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
