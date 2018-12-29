"""Synchronization primitives among tasks.

NOTE: The primitives defined in this module are **NOT** thread-safe.
You should only use them among tasks spawned from the same kernel.
"""

__all__ = [
    'Condition',
    'Event',
    'Lock',
]

from g1.bases.assertions import ASSERT

from . import contexts
from . import traps


class Lock:

    def __init__(self):
        self._locked = False

    def __repr__(self):
        return '<%s at %#x: %s>' % (
            self.__class__.__qualname__,
            id(self),
            'locked' if self._locked else 'unlocked',
        )

    async def __aenter__(self):
        # Unlike ``threading.Lock``, here we return the object.
        await self.acquire()
        return self

    async def __aexit__(self, *_):
        self.release()

    def is_owner(self):
        """Return true if the current task is the owner of this lock.

        Only an owner may release a lock.  This check is mostly useful
        internally.
        """
        # NOTE: For a ``Lock``, any task owns a locked lock, but for an
        # ``RLock``, only the task that has locked it is its owner.
        return self._locked

    async def acquire(self, blocking=True):
        """Acquire the lock and return true when locked is acquired."""
        if not blocking:
            return self.acquire_nonblocking()
        while self._locked:
            await traps.block(self)
        self._locked = True
        return True

    def acquire_nonblocking(self):
        """Non-blocking version of ``acquire``."""
        if self._locked:
            return False
        else:
            self._locked = True
            return True

    def release(self):
        ASSERT.true(self.is_owner())
        self._locked = False
        contexts.get_kernel().unblock(self)


class Condition:

    def __init__(self, lock=None):
        self._lock = lock or Lock()
        self._waiters = set()
        # Re-export these methods.
        self.acquire = self._lock.acquire
        self.acquire_nonblocking = self._lock.acquire_nonblocking
        self.release = self._lock.release

    def __repr__(self):
        return '<%s at %#x: %r>' % (
            self.__class__.__qualname__,
            id(self),
            self._lock,
        )

    async def __aenter__(self):
        # Unlike ``threading.Condition``, here we return the object.
        await self._lock.__aenter__()
        return self

    async def __aexit__(self, *args):
        return await self._lock.__aexit__(*args)

    async def wait(self):
        """Wait until notified.

        Unlike ``threading.Condition.wait`` (which returns a boolean),
        this method does not return any value.
        """
        ASSERT.true(self._lock.is_owner())
        waiter = Lock()
        ASSERT.true(waiter.acquire_nonblocking())
        self._waiters.add(waiter)
        # NOTE: We have not implemented ``RLock`` yet, but when we do,
        # be careful **NOT** to call ``release`` here, since you cannot
        # unlock the lock acquired recursively.
        self._lock.release()
        try:
            await waiter.acquire()
        finally:
            await self._lock.acquire()

    def notify(self, n=1):
        ASSERT.true(self._lock.is_owner())
        for _ in range(n):
            self._waiters.pop().release()

    def notify_all(self):
        self.notify(len(self._waiters))


class Event:

    def __init__(self):
        self._condition = Condition()
        self._flag = False

    def __repr__(self):
        return '<%s at %#x: %s>' % (
            self.__class__.__qualname__,
            id(self),
            'set' if self._flag else 'unset',
        )

    def is_set(self):
        return self._flag

    def set(self):
        ASSERT.true(self._condition.acquire_nonblocking())
        try:
            self._flag = True
            self._condition.notify_all()
        finally:
            self._condition.release()

    def clear(self):
        self._flag = False

    async def wait(self):
        async with self._condition:
            if not self._flag:
                await self._condition.wait()
            return self._flag
