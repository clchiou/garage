"""Filesystem extended attribute functions."""

#
# NOTE: For now we do not implement symlink variant of the functions,
# e.g., lgetxattr, because they are not very useful.
#

__all__ = [
    'XATTR_CREATE',
    'XATTR_REPLACE',
    'getxattr',
    'listxattr',
    'removexattr',
    'setxattr',
]

import ctypes
import errno
import os
from pathlib import Path
from typing import Sequence, Union

from . import _xattrs
# Re-export these.
from ._xattrs import XATTR_CREATE
from ._xattrs import XATTR_REPLACE


def listxattr(
    path_or_fd: Union[Path, bytes, int, str],
    *,
    encoding: Union[None, str] = 'utf-8',
) -> Union[Sequence[str], Sequence[bytes]]:
    listxattr_func, arg0 = _select_variant(
        path_or_fd, _xattrs.listxattr, _xattrs.flistxattr
    )
    attrs = _read_bytes('listxattr', listxattr_func, (arg0, )).split(b'\x00')
    if encoding is not None:
        attrs = [attr.decode(encoding) for attr in attrs]
    return attrs


def getxattr(
    path_or_fd: Union[Path, bytes, int, str],
    name: Union[bytes, str],
) -> Union[bytes, None]:
    getxattr_func, arg0 = _select_variant(
        path_or_fd, _xattrs.getxattr, _xattrs.fgetxattr
    )
    if isinstance(name, str):
        name_str, name_bytes = name, name.encode('utf-8')
    else:
        name_str, name_bytes = name.decode('utf-8'), name
    try:
        return _read_bytes(name_str, getxattr_func, (arg0, name_bytes))
    except OSError as exc:
        if exc.errno == errno.ENODATA:
            return None
        raise


def setxattr(
    path_or_fd: Union[Path, bytes, int, str],
    name: Union[bytes, str],
    value: bytes,
    flags: int = 0,
):
    setxattr_func, arg0 = _select_variant(
        path_or_fd, _xattrs.setxattr, _xattrs.fsetxattr
    )
    if isinstance(name, str):
        name = name.encode('utf-8')
    setxattr_func(arg0, name, value, len(value), flags)


def removexattr(
    path_or_fd: Union[Path, bytes, int, str],
    name: Union[bytes, str],
):
    removexattr_func, arg0 = _select_variant(
        path_or_fd, _xattrs.removexattr, _xattrs.fremovexattr
    )
    if isinstance(name, str):
        name = name.encode('utf-8')
    removexattr_func(arg0, name)


def _select_variant(path_or_fd, path_variant, fd_variant):
    if isinstance(path_or_fd, int):
        return fd_variant, path_or_fd
    elif isinstance(path_or_fd, bytes):
        return path_variant, path_or_fd
    else:
        return path_variant, os.fspath(path_or_fd).encode('utf-8')


def _read_bytes(name, func, args, buffer_size=256, buffer_size_limit=65536):
    while True:
        buffer = ctypes.create_string_buffer(buffer_size)
        try:
            size = func(*args, buffer, buffer_size)
        except OSError as exc:
            if exc.errno != errno.ERANGE:
                raise
        else:
            return buffer.raw[:size]
        buffer_size *= 2
        if buffer_size > buffer_size_limit:
            raise ValueError(
                'size of %s exceeds %d' % (name, buffer_size_limit)
            )
