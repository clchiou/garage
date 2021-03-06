__all__ = [
    'FileLock',
]

import errno
import fcntl
import os

from garage import scripts
from garage.assertions import ASSERT


class FileLock:
    """Non-reentrant, non-blocking file lock."""

    def __init__(self, lock_file_path):
        self._lock_file_path = lock_file_path
        self._fd = None

    @property
    def locked(self):
        return self._fd is not None

    def acquire(self):
        if scripts.is_dry_run():
            return True

        ASSERT.false(self.locked)

        if not self._lock_file_path.exists():
            with scripts.using_sudo():
                scripts.mkdir(self._lock_file_path.parent)
                scripts.execute(['touch', self._lock_file_path])

        fd = os.open(str(self._lock_file_path), os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            if exc.errno != errno.EWOULDBLOCK:
                raise
            return False
        else:
            fd, self._fd = None, fd
            return True
        finally:
            if fd is not None:
                os.close(fd)

    def release(self):
        if scripts.is_dry_run():
            return

        ASSERT.true(self.locked)

        fd, self._fd = self._fd, None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
