"""Low-level filesystem extended attribute functions."""

__all__ = [
    # list
    'flistxattr',
    'listxattr',
    'llistxattr',
    # get
    'fgetxattr',
    'getxattr',
    'lgetxattr',
    # set
    'XATTR_CREATE',
    'XATTR_REPLACE',
    'fsetxattr',
    'lsetxattr',
    'setxattr',
    # remove
    'fremovexattr',
    'lremovexattr',
    'removexattr',
]

import ctypes
import ctypes.util
import os

from g1.bases import functionals

XATTR_CREATE = 1
XATTR_REPLACE = 2

# Sadly ctypes.cdll.LoadLibrary does not set use_errno to True.
_LIBC = ctypes.CDLL(ctypes.util.find_library('libc'), use_errno=True)


def _check(rc):
    if rc < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
    return rc


def _load(name, argtypes, restype):
    func = _LIBC[name]
    func.argtypes = argtypes
    func.restype = restype
    return functionals.compose(_check, func)


def _load_variants(base_name, common_argtypes, restype):
    return (
        _load(base_name, (ctypes.c_char_p, ) + common_argtypes, restype),
        _load('l' + base_name, (ctypes.c_char_p, ) + common_argtypes, restype),
        _load('f' + base_name, (ctypes.c_int, ) + common_argtypes, restype),
    )


listxattr, llistxattr, flistxattr = _load_variants(
    'listxattr',
    # list, size
    (ctypes.c_char_p, ctypes.c_size_t),
    ctypes.c_ssize_t,
)

getxattr, lgetxattr, fgetxattr = _load_variants(
    'getxattr',
    # name, value, size
    (ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t),
    ctypes.c_ssize_t,
)

#
# NOTE: "user" extended attributes are allowed only for regular files
# and directories.
#

setxattr, lsetxattr, fsetxattr = _load_variants(
    'setxattr',
    # name, value, size, flags
    (ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int),
    ctypes.c_int,
)

removexattr, lremovexattr, fremovexattr = _load_variants(
    'removexattr',
    # name
    (
        ctypes.c_char_p,
    ),
    ctypes.c_int,
)
