__all__ = [
    'make_read_write_lock',
]

import threading

from g1.bases.assertions import ASSERT


def make_read_write_lock():
    rwlock = ReadWriteLock()
    return (
        LockLike(rwlock.reader_acquire, rwlock.reader_release),
        LockLike(rwlock.writer_acquire, rwlock.writer_release),
    )


class LockLike:

    def __init__(self, acquire, release):
        self.acquire = acquire
        self.release = release

    def __enter__(self):
        self.acquire()

    def __exit__(self, *_):
        self.release()


class ReadWriteLock:
    """Readers-writer lock.

    The writer part of the lock is pretty much like an ordinary lock,
    but the readers part of the lock, at the current implementation, is
    somehow like a reentrant lock (the same thread may acquire a reader
    lock multiple times).

    NOTE: stdlib's Lock.acquire takes both blocking and timeout
    arguments even though just timeout is sufficient in all use cases.
    I think the blocking argument is there just to maintain backward
    compatibility.  stdlib's Lock.acquire's interface is complicated
    because of this; so I would prefer omitting blocking argument,
    breaking compatibility with stdlib.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._reader_cond = threading.Condition(self._lock)
        self._num_readers = 0
        self._writer_cond = threading.Condition(self._lock)
        self._num_writers = 0

    def reader_acquire(self, *, timeout=None):
        with self._lock:
            if not self._reader_cond.wait_for(
                lambda: self._num_writers == 0,
                timeout=timeout,
            ):
                return False
            self._num_readers += 1
            return True

    def reader_release(self):
        with self._lock:
            ASSERT.greater(self._num_readers, 0)
            ASSERT.equal(self._num_writers, 0)
            self._num_readers -= 1
            if self._num_readers == 0:
                self._writer_cond.notify()

    def writer_acquire(self, *, timeout=None):
        with self._lock:
            if not self._writer_cond.wait_for(
                lambda: self._num_readers == 0 and self._num_writers == 0,
                timeout=timeout,
            ):
                return False
            self._num_writers += 1
            return True

    def writer_release(self):
        with self._lock:
            ASSERT.equal(self._num_readers, 0)
            ASSERT.equal(self._num_writers, 1)
            self._num_writers = 0
            self._reader_cond.notify_all()
            self._writer_cond.notify()
