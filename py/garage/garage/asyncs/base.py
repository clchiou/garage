"""Low-level hacks to curio."""

__all__ = [
    'Event',
]

import curio.sched
import curio.traps


class Event:
    """An implementation of Event to replace curio.Event.

       Compared to curio.Event, the advantage of this implementation is
       that both set() and clear() are not async, making its interface
       more consistent and more convenient to use than curio.Event's.
    """

    __slots__ = ('_set', '_kernel', '_waiting')

    def __init__(self):
        self._set = False
        self._kernel = None
        self._waiting = curio.sched.SchedBarrier()

    def __repr__(self):
        return '<%s [%s,waiters:%d]>' % (
            super().__repr__()[1:-1],
            'set' if self._set else 'unset',
            len(self._waiting),
        )

    def is_set(self):
        return self._set

    def set(self):
        self._set = True
        if self._kernel:
            for task in self._waiting.pop(len(self._waiting)):
                # Copy _rescuedule_task() from curio/kernel.py
                self._kernel._ready.append(task)
                task.next_value = None
                task.next_exc = None
                task.state = 'READY'
                task.cancel_func = None

    def clear(self):
        self._set = False

    async def wait(self):
        if self._set:
            return
        if self._kernel is None:
            self._kernel = await curio.traps._get_kernel()
        await curio.traps._scheduler_wait(self._waiting, 'EVENT_WAIT')
