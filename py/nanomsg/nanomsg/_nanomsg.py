__all__ = [
    'nn_symbol_properties',
    'nn_iovec',
    'nn_msghdr',
    'nn_pollfd',
    # Extend in _load()
]

import ctypes
from ctypes import POINTER, c_char_p, c_int, c_short, c_size_t, c_void_p


_LIBNANOMSG = ctypes.cdll.LoadLibrary('libnanomsg.so')


# NOTE: Definitions below are targeting nanomsg 1.0.0.


class nn_symbol_properties(ctypes.Structure):
    _fields_ = [
        ('value', c_int),
        ('name', c_char_p),
        ('ns', c_int),
        ('type', c_int),
        ('unit', c_int),
    ]


class nn_iovec(ctypes.Structure):
    _fields_ = [
        ('iov_base', c_void_p),
        ('iov_len', c_size_t),
    ]


class nn_msghdr(ctypes.Structure):
    _fields_ = [
        ('msg_iov', POINTER(nn_iovec)),
        ('msg_iovlen', c_int),
        ('msg_control', c_void_p),
        ('msg_controllen', c_size_t),
    ]


class nn_pollfd(ctypes.Structure):
    _fields = [
        ('fd', c_int),
        ('events', c_short),
        ('revents', c_short),
    ]


def _load(libnanomsg, global_vars, exposed_names):
    #
    # NOTE: Use c_void_p instead of c_char_p so that Python does not
    # convert variables to/from bytes automatically.  While this might
    # be inconvenient, it is probably the correct behavior (especially
    # for nn_allocmsg allocated space).
    #
    decls = [
        # Errors.
        ('nn_errno', [], c_int),
        ('nn_strerror', [c_int], c_char_p),
        # Symbols.
        ('nn_symbol', [c_int, POINTER(c_int)], c_char_p),
        ('nn_symbol_info',
         [c_int, POINTER(nn_symbol_properties), c_int], c_int),
        # Helper function for shutting down multi-threaded applications.
        ('nn_term', [], None),
        # Zero-copy support.
        ('nn_allocmsg', [c_size_t, c_int], c_void_p),
        ('nn_reallocmsg', [c_void_p, c_size_t], c_void_p),
        ('nn_freemsg', [c_void_p], c_int),
        # Socket definition.
        ('nn_socket', [c_int, c_int], c_int),
        ('nn_close', [c_int], c_int),
        ('nn_setsockopt',
         [c_int, c_int, c_int, c_void_p, c_size_t], c_int),
        ('nn_getsockopt',
         [c_int, c_int, c_int, c_void_p, POINTER(c_size_t)], c_int),
        ('nn_bind', [c_int, c_char_p], c_int),
        ('nn_connect', [c_int, c_char_p], c_int),
        ('nn_shutdown', [c_int, c_int], c_int),
        ('nn_send', [c_int, c_void_p, c_size_t, c_int], c_int),
        ('nn_recv', [c_int, c_void_p, c_size_t, c_int], c_int),
        ('nn_sendmsg', [c_int, POINTER(nn_msghdr), c_int], c_int),
        ('nn_recvmsg', [c_int, POINTER(nn_msghdr), c_int], c_int),
        # Socket mutliplexing support.
        ('nn_poll', [POINTER(nn_pollfd), c_int, c_int], c_int),
        # Built-in support for devices.
        ('nn_device', [c_int, c_int], c_int),
    ]

    for name, argtypes, restype in decls:
        func = getattr(libnanomsg, name)
        func.argtypes = argtypes
        func.restype = restype
        global_vars[name] = func

    exposed_names.extend(name for name, _, _ in decls)

    if len(set(exposed_names)) != len(exposed_names):
        raise AssertionError('names conflict: %r' % exposed_names)


_load(_LIBNANOMSG, globals(), __all__)
