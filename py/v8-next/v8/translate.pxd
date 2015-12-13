from v8 cimport (
    Local,
    Value,
    _Context,
)


cdef js2py(Local[_Context] context, Local[Value] value)
