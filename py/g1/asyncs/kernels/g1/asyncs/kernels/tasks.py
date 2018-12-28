__all__ = [
    'Task',
]

import inspect
import logging
import weakref

from g1.bases.assertions import ASSERT

from . import contexts
from . import errors
from . import traps

LOG = logging.getLogger(__name__)


class Task:
    """Task object.

    A ``Task`` object wraps an coroutine object, and is the basic unit
    of scheduling.  It is modelled after ``Future` object, which is
    commonly used for wrapping a ``Thread`` object.  There are a few
    notable differences between ``Task`` and ``Future``:

    * ``Task`` is cancellable due to its cooperative nature, but
      ``Future`` is not because threads in general are not cancellable.

    * ``get_result`` and ``get_exception`` does not take a ``timeout``
      argument.  While it is possible to add a ``timeout`` argument, as
      a convention we would prefer not to.
    """

    @staticmethod
    def is_coroutine(coro):
        # ``types.coroutine`` returns a generator function.
        return inspect.iscoroutine(coro) or inspect.isgenerator(coro)

    def __init__(self, coroutine):
        self._coroutine = ASSERT.predicate(coroutine, self.is_coroutine)
        self._num_ticks = 0
        self._completed = False
        self._result = None
        self._exception = None
        self._callbacks = []
        # Extra debug info (pre-format it to prevent it from leaking
        # into logging sub-system).
        task_repr = '<%s at %#x: %r, ...>' % (
            self.__class__.__qualname__,
            id(self),
            self._coroutine,
        )
        self._finalizer = weakref.finalize(
            self,
            LOG.warning,
            'task is garbage-collected but never joined: %s',
            task_repr,
        )

    def __repr__(self):
        return '<%s at %#x: %r, ticks=%d, %s, %r, %r>' % (
            self.__class__.__qualname__,
            id(self),
            self._coroutine,
            self._num_ticks,
            'completed' if self._completed else 'uncompleted',
            self._result,
            self._exception,
        )

    def is_completed(self):
        return self._completed

    def cancel(self):
        # Add ``Task.cancel`` for convenience.
        contexts.get_kernel().cancel(self)

    async def join(self):
        self._finalizer.detach()
        await traps.join(self)

    async def get_result(self):
        await self.join()
        return self.get_result_nonblocking()

    async def get_exception(self):
        await self.join()
        return self.get_exception_nonblocking()

    def get_result_nonblocking(self):
        ASSERT.true(self.is_completed())
        self._finalizer.detach()
        if self._exception:
            raise self._exception
        else:
            return self._result

    def get_exception_nonblocking(self):
        ASSERT.true(self.is_completed())
        self._finalizer.detach()
        return self._exception

    #
    # Package-private interface.
    #

    def tick(self, trap_result, trap_exception):
        """Run coroutine through the next trap point."""
        ASSERT.false(self.is_completed())
        if trap_exception:
            func = self._coroutine.throw
            arg = trap_exception
        else:
            func = self._coroutine.send
            arg = trap_result
        try:
            self._num_ticks += 1
            trap = func(arg)
        except errors.TaskCancellation:
            self._completed = True
            self._exception = errors.Cancelled
        except StopIteration as exc:
            self._completed = True
            self._result = exc.value
        except BaseException as exc:
            self._completed = True
            self._exception = exc
        else:
            return ASSERT.not_none(trap)
        ASSERT.true(self._completed)
        callbacks, self._callbacks = self._callbacks, None
        for callback in callbacks:
            self._call_callback(callback)
        return None

    def add_callback(self, callback):
        if self._completed:
            self._call_callback(callback)
        else:
            self._callbacks.append(callback)

    def _call_callback(self, callback):
        try:
            callback(self)
        except Exception:
            LOG.exception('callback err: %r, %r', self, callback)
