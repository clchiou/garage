__all__ = [
    'Future',
]

import logging

from g1.asyncs.kernels import errors
from g1.bases import classes
from g1.bases.assertions import ASSERT

from . import locks

LOG = logging.getLogger(__name__)


class Future:
    """Asynchronous future.

    Generally a task object is sufficient for most use cases, but in the
    rare cases that you do need a future object, here it is.

    Also, this future class is compatible with task; it can be used in
    CompletionQueue.
    """

    def __init__(self):
        self._completed = locks.Event()
        self._result = None
        self._exception = None
        self._callbacks = []
        self._consumed = False
        self._finalizer = None

    def __del__(self):
        if not (
            self._completed.is_set() and self._exception is None
            and not self._consumed
        ):
            return
        if self._finalizer is not None:
            try:
                self._finalizer(self._result)
            except BaseException:
                LOG.exception('finalizer error')
            return
        # Make a special case for None.
        if self._result is None:
            return
        LOG.warning(
            'future is garbage-collected but result is never consumed: %s',
            # Call repr to format self here to avoid resurrecting self.
            repr(self),
        )

    __repr__ = classes.make_repr(
        '{state} {self._result!r} {self._exception!r}',
        state=lambda self: 'completed'
        if self.is_completed() else 'uncompleted',
    )

    def is_completed(self):
        return self._completed.is_set()

    async def get_result(self):
        await self.join()
        return self.get_result_nonblocking()

    async def get_exception(self):
        await self.join()
        return self.get_exception_nonblocking()

    def get_result_nonblocking(self):
        ASSERT.true(self.is_completed())
        self._consumed = True
        if self._exception:
            raise self._exception
        return self._result

    def get_exception_nonblocking(self):
        ASSERT.true(self.is_completed())
        self._consumed = True
        return self._exception

    def set_finalizer(self, finalizer):
        """Set finalizer.

        The finalizer is called when future's result is set but is never
        consumed.  You may use finalizer to release the result object.
        """
        self._finalizer = finalizer

    def set_result(self, result):
        self._set_result_or_exception(result, None)

    def set_exception(self, exception):
        self._set_result_or_exception(None, exception)

    def _set_result_or_exception(self, result, exception):
        if self.is_completed():
            if exception:
                LOG.error('ignore exception: %r', self, exc_info=exception)
            else:
                LOG.error('ignore result: %r, %r', self, result)
            return
        self._result = result
        self._exception = exception
        self._completed.set()
        callbacks, self._callbacks = self._callbacks, None
        for callback in callbacks:
            self._call_callback(callback)

    #
    # Task-compatibility interface.
    #

    async def join(self):
        await self._completed.wait()

    def cancel(self):
        self.set_exception(errors.Cancelled())

    def add_callback(self, callback):
        if self.is_completed():
            self._call_callback(callback)
        else:
            self._callbacks.append(callback)

    def _call_callback(self, callback):
        try:
            callback(self)
        except Exception:
            LOG.exception('callback err: %r, %r', self, callback)
