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


#
# To pass a Python object to a C function as a ``void *`` (usually as
# the Python callback data), you need an extra level of indirection due
# to the limitations that ``ctypes`` imposes; namely ``addressof`` and
# ``byref`` only accepts ``_ctypes._CData`` instances.
#
# (Otherwise I imagine we could do something like ``byref(obj)`` when
# registering a callback, and simply do ``py_object(addr).value`` to
# dereference it.  Anyway.)
#
# You will need to wrap your Python object in a ``py_object`` object,
# which is a ``_ctypes._CData`` sub-class instance, and then take the
# pointer to the ``py_object`` object with ``byref``.
#
# To dereference it, you cast it to ``POINTER(py_object)``.
#
# NOTE: Remember to also "own" the ``py_object`` object in additional to
# your Python object; otherwise the ``py_object`` object may be freed,
# resulting in use-after-free corruption.
#
py_object_p = ctypes.POINTER(ctypes.py_object)


def deref_py_object_p(addr):
    return ctypes.cast(addr, py_object_p).contents.value
