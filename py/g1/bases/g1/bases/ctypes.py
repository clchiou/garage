"""Extension of standard library's ctypes."""

__all__ = [
    'PyBUF_READ',
    'PyBUF_WRITE',
    'PyMemoryView_FromMemory',
    'c_blob',
    'deref_py_object_p',
    'load_func',
    'py_object_p',
]

import ctypes

PyBUF_READ = 0x100
PyBUF_WRITE = 0x200

PyMemoryView_FromMemory = ctypes.pythonapi.PyMemoryView_FromMemory
PyMemoryView_FromMemory.argtypes = (
    ctypes.c_void_p,
    ctypes.c_ssize_t,
    ctypes.c_int,
)
PyMemoryView_FromMemory.restype = ctypes.py_object

# Represent not NULL-terminated strings.
# See: https://docs.python.org/3/library/ctypes.html#ctypes.c_char_p
c_blob = ctypes.POINTER(ctypes.c_char)


def load_func(library, name, restype, argtypes):
    func = library[name]
    func.argtypes = argtypes
    func.restype = restype
    return func


# ``py_object`` itself is a pointer type: ``PyObject *``.
py_object_p = ctypes.POINTER(ctypes.py_object)


def deref_py_object_p(addr):
    """Equivalent to ``*(PyObject **)addr``."""
    return ctypes.cast(addr, py_object_p).contents.value
