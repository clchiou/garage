__all__ = [
    'Task',
]

import inspect
import logging
import sys

from g1.bases import classes
from g1.bases.assertions import ASSERT

from . import errors
from . import traps

LOG = logging.getLogger(__name__)

# Python 3.4 implements PEP 442 for safe ``__del__``.
ASSERT.greater_or_equal(sys.version_info, (3, 4))


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

    NOTE: Although task is cancellable, this should be the last resort
    because a cancel only takes effect on the task's next blocking trap,
    and this may take much longer than desired; for example, if a task
    is sending through a socket and the socket's buffer is somehow never
    full, this task may never be blocked and stay running forever.
    """

    @staticmethod
    def is_coroutine(coro):
        # ``types.coroutine`` returns a generator function.
        return inspect.iscoroutine(coro) or inspect.isgenerator(coro)

    def __init__(self, kernel, coroutine):
        self._kernel = kernel
        self._coroutine = ASSERT.predicate(coroutine, self.is_coroutine)
        self._num_ticks = 0
        self._completed = False
        self._result = None
        self._exception = None
        self._callbacks = []
        self._joined = False

    def __del__(self):
        if not self._joined:
            LOG.warning('task is garbage-collected but never joined: %r', self)

    __repr__ = classes.make_repr(
        '{self._coroutine!r} ticks={self._num_ticks} '
        '{state} {self._result!r} {self._exception!r}',
        state=lambda self: 'completed' if self._completed else 'uncompleted',
    )

    def is_completed(self):
        return self._completed

    def cancel(self):
        # Add ``Task.cancel`` for convenience.
        self._kernel.cancel(self)

    async def join(self):
        self._joined = True
        await traps.join(self)

    async def get_result(self):
        await self.join()
        return self.get_result_nonblocking()

    async def get_exception(self):
        await self.join()
        return self.get_exception_nonblocking()

    def get_result_nonblocking(self):
        ASSERT.true(self.is_completed())
        self._joined = True
        if self._exception:
            raise self._exception
        else:
            return self._result

    def get_exception_nonblocking(self):
        ASSERT.true(self.is_completed())
        self._joined = True
        return self._exception

    #
    # Package-private interface.
    #

    def tick(self, trap_result, trap_exception):
        """Run coroutine through the next trap point.

        NOTE: ``tick`` catches ``BaseException`` raised from the
        coroutine.  As a result, ``SystemExit`` does not bubble up to
        the kernel event loop.  I believe this behavior is similar to
        Python threading library and thus more expected (``SystemExit``
        raised in non- main thread does not cause CPython process to
        exit).  If you want raising ``SystemExit`` in a task to be
        effective, you have to call ``Task.get_result_nonblocking`` in
        the main thread (or implicitly through ``Kernel.run``).
        """
        ASSERT.false(self._completed)
        if trap_exception:
            trap = self._tick(self._coroutine.throw, trap_exception)
        else:
            trap = self._tick(self._coroutine.send, trap_result)
        if trap is not None:
            return trap
        ASSERT.true(self._completed)
        self._call_callbacks()
        return None

    def abort(self):
        """Close the running coroutine.

        This is the last resort for releasing resources acquired by the
        coroutine, not a part of normal task cleanup.  One good place to
        call ``abort`` is when kernel is closing.
        """
        if self._completed:
            return
        LOG.debug('abort task: %r', self)
        ASSERT.none(self._tick(self._coroutine.close))
        if not self._completed:
            self._completed = True
            self._exception = errors.Cancelled('task abort')
        self._call_callbacks()

    def _tick(self, func, *args):
        try:
            self._num_ticks += 1
            return func(*args)
        except errors.TaskCancellation as exc:
            self._completed = True
            self._exception = errors.Cancelled()
            self._exception.__cause__ = exc
        except StopIteration as exc:
            self._completed = True
            self._result = exc.value
        except BaseException as exc:
            self._completed = True
            self._exception = exc
        return None

    def _call_callbacks(self):
        ASSERT.true(self._completed)
        callbacks, self._callbacks = self._callbacks, None
        for callback in callbacks:
            self._call_callback(callback)

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
