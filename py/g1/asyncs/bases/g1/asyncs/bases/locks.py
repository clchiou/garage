"""Synchronization primitives among tasks.

NOTE: The primitives defined in this module are **NOT** thread-safe.
You should only use them among tasks spawned from the same kernel.
"""

__all__ = [
    'BoundedSemaphore',
    'Condition',
    'Event',
    'Gate',
    'Lock',
    'Semaphore',
]

from g1.asyncs.kernels import contexts
from g1.asyncs.kernels import traps
from g1.bases import classes
from g1.bases.assertions import ASSERT


class Lock:

    def __init__(self):
        self._locked = False

    __repr__ = classes.make_repr(
        '{state}',
        state=lambda self: 'locked' if self._locked else 'unlocked',
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

    __repr__ = classes.make_repr('{self._lock!r}')

    async def __aenter__(self):
        # Unlike ``threading.Condition``, here we return the object.
        await self._lock.__aenter__()
        return self

    async def __aexit__(self, *args):
        return await self._lock.__aexit__(*args)

    async def wait(self):
        """Wait until notified.

        To be somehow compatible with ``threading.Condition.wait``, this
        always return true (since it never times out).
        """
        ASSERT.true(self._lock.is_owner())
        waiter = Gate()
        self._waiters.add(waiter)
        # NOTE: We have not implemented ``RLock`` yet, but when we do,
        # be careful **NOT** to call ``release`` here, since you cannot
        # unlock the lock acquired recursively.
        self._lock.release()
        try:
            await waiter.wait()
        finally:
            await self._lock.acquire()
        return True

    def notify(self, n=1):
        ASSERT.true(self._lock.is_owner())
        for _ in range(min(n, len(self._waiters))):
            self._waiters.pop().unblock()

    def notify_all(self):
        self.notify(len(self._waiters))


class Event:

    def __init__(self):
        self._flag = False

    __repr__ = classes.make_repr(
        '{state}',
        state=lambda self: 'set' if self._flag else 'unset',
    )

    def is_set(self):
        return self._flag

    def set(self):
        self._flag = True
        # Let's make a special case when no task is waiting for this
        # event object (with this, you may call ``Event.set`` out of a
        # kernel context).  This is useful when you want to initialize
        # events before a kernel context is initialized.
        try:
            contexts.get_kernel().unblock(self)
        except LookupError:
            pass

    def clear(self):
        self._flag = False

    async def wait(self):
        while not self._flag:
            await traps.block(self)
        return self._flag


class Gate:
    """Expose kernel's block/unblock interface.

    This is an "empty" class that it only uses ``self`` as the blocker
    source; this is probably not very memory-efficient, but should be
    okay for now.
    """

    __slots__ = ()

    def unblock(self):
        """Unblock current waiters."""
        # Let's make a special case for calling ``unblock`` out of a
        # kernel context.
        try:
            contexts.get_kernel().unblock(self)
        except LookupError:
            pass

    async def wait(self):
        """Wait until ``unblock`` is called."""
        await traps.block(self)


class Semaphore:

    def __init__(self, value=1):
        self._value = ASSERT.greater_or_equal(value, 0)
        self._gate = Gate()

    async def __aenter__(self):
        # Unlike ``threading.Semaphore``, here we return the object.
        await self.acquire()
        return self

    async def __aexit__(self, *_):
        self.release()

    async def acquire(self, blocking=True):
        if blocking:
            while self._value == 0:
                await self._gate.wait()
        return self.acquire_nonblocking()

    def acquire_nonblocking(self):
        if self._value == 0:
            return False
        self._value -= 1
        return True

    def release(self, n=1):
        self._value += ASSERT.greater_or_equal(n, 1)
        self._gate.unblock()


class BoundedSemaphore(Semaphore):

    def __init__(self, value=1):
        super().__init__(value)
        self.__upper_bound = value

    def release(self, n=1):
        ASSERT.less_or_equal(self._value + n, self.__upper_bound)
        return super().release(n)
