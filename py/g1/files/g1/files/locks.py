__all__ = [
    'FileLock',
    'NotLocked',
    'acquiring_exclusive',
    'acquiring_shared',
    'try_acquire_exclusive',
    'is_locked_by_other',
]

import contextlib
import errno
import fcntl
import os

from g1.bases.assertions import ASSERT


class NotLocked(Exception):
    """Raise when file lock cannot be acquired."""


class FileLock:

    def __init__(self, path, *, close_on_exec=True):
        fd = os.open(path, os.O_RDONLY)
        try:
            # Actually, CPython's os.open always sets O_CLOEXEC.
            flags = fcntl.fcntl(fd, fcntl.F_GETFD)
            if close_on_exec:
                new_flags = flags | fcntl.FD_CLOEXEC
            else:
                new_flags = flags & ~fcntl.FD_CLOEXEC
            if new_flags != flags:
                fcntl.fcntl(fd, fcntl.F_SETFD, new_flags)
        except:
            os.close(fd)
            raise
        self._fd = fd

    def acquire_shared(self):
        self._acquire(fcntl.LOCK_SH)

    def acquire_exclusive(self):
        self._acquire(fcntl.LOCK_EX)

    def _acquire(self, operation):
        ASSERT.not_none(self._fd)
        # TODO: Should we add a retry here?
        try:
            fcntl.flock(self._fd, operation | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            if exc.errno != errno.EWOULDBLOCK:
                raise
            raise NotLocked from None

    def release(self):
        """Release file lock.

        It is safe to call release even if lock has not been acquired.
        """
        ASSERT.not_none(self._fd)
        fcntl.flock(self._fd, fcntl.LOCK_UN)

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


@contextlib.contextmanager
def acquiring_shared(path):
    lock = FileLock(path)
    try:
        lock.acquire_shared()
        yield lock
    finally:
        lock.release()
        lock.close()


@contextlib.contextmanager
def acquiring_exclusive(path):
    lock = FileLock(path)
    try:
        lock.acquire_exclusive()
        yield lock
    finally:
        lock.release()
        lock.close()


def try_acquire_exclusive(path):
    lock = FileLock(path)
    try:
        lock.acquire_exclusive()
    except NotLocked:
        lock.close()
        return None
    else:
        return lock


def is_locked_by_other(path):
    lock = try_acquire_exclusive(path)
    if lock:
        lock.release()
        lock.close()
        return False
    else:
        return True
