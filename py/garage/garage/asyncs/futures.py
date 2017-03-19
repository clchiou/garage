"""
Future objects that represent one-shot caller-callee contract.  A caller
will hold a Future object and its callee will hold a Promise object.

Direct caller-callee relationship where a caller has direct reference to
its callee should be modelled by normal function call or task spawning.
Future objects should be for indirect caller-callee relationship; for
example, a caller submits jobs to a worker pool and cannot be certain
which worker will be performing the job, and in this case we should use
Future objects to model the caller-callee relationship.
"""

__all__ = [
    'CancelledError',
    'Future',
    'FutureAdapter',
]

from concurrent.futures import CancelledError
import enum

import curio.traps

from . import base


class State(enum.Enum):
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    CANCELLED = 'CANCELLED'
    FINISHED = 'FINISHED'


class Future:
    """Future object, which is for the caller-side of the contract.

       NOTE: The interface of Future class is still different from that
       of concurrent.futures.Future, but we try to make them as close as
       possible/practical.
    """

    # You should not construct Promise objects directly, and should call
    # Future.make_promise to get Promise objects.
    class Promise:
        """Promise object, which is for the callee-side of the contract.

           NOTE: Interface of the Promise object is not asynchronous;
           meaning that you may use it outside of an event loop (say, in
           a work thread performing blocking operations).
        """

        def __init__(self, future):
            self._future = future

        # It's usually a good idea that you check whether the job has
        # been cancelled before starting it.
        def set_running_or_notify_cancel(self):
            if self._future._state is State.CANCELLED:
                return False
            elif self._future._state is State.PENDING:
                self._future._state = State.RUNNING
                return True
            else:
                raise AssertionError(
                    'Future is in unexpected state: %r' % self._future._state)

        def cancelled(self):
            return self._future.cancelled()

        def _set(self, result, exception):
            if self._future._state is State.CANCELLED:
                return
            elif self._future._state is State.FINISHED:
                raise AssertionError(
                    'Future has been marked FINISHED: %r' % self._future)
            else:
                assert not self._future.done()
                assert not self._future._done.is_set()
                self._future._result = result
                self._future._exception = exception
                self._future._state = State.FINISHED
                self._future._done.set()

        def set_result(self, result):
            self._set(result, None)

        def set_exception(self, exception):
            self._set(None, exception)

    def __init__(self):
        # Set when state is transition to CANCELED or FINISHED
        self._done = base.Event()
        self._state = State.PENDING
        self._result = None
        self._exception = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.cancel()

    def running(self):
        return self._state is State.RUNNING

    def cancelled(self):
        return self._state is State.CANCELLED

    def done(self):
        return self._state in (State.CANCELLED, State.FINISHED)

    def promise(self):
        # Future won't reference to Promise to avoid cyclic reference.
        return Future.Promise(self)

    def cancel(self):
        """Notify the Promise holder that the Future holder is not
           interested in the result anymore.

           Return True if the future is/was actually cancelled.
        """
        if self._state is State.PENDING:
            self._state = State.CANCELLED
            self._done.set()
            return True
        elif self._state is State.RUNNING:
            return False
        elif self._state is State.CANCELLED:
            assert self._done.is_set()
            return True
        else:
            assert self._state is State.FINISHED
            assert self._done.is_set()
            return False

    async def result(self):
        await self._done.wait()
        assert self.done()
        if self._state is State.CANCELLED:
            raise CancelledError
        elif self._exception is not None:
            raise self._exception
        else:
            return self._result

    async def exception(self):
        await self._done.wait()
        assert self.done()
        if self._state is State.CANCELLED:
            raise CancelledError
        else:
            return self._exception


class FutureAdapter:
    """An asynchronous interface adapter for a concurrent.futures.Future
       objects.
    """

    def __init__(self, future):
        self._future = future

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.cancel()

    def running(self):
        return self._future.running()

    def cancelled(self):
        return self._future.cancelled()

    def done(self):
        return self._future.done()

    def cancel(self):
        return self._future.cancel()

    async def result(self):
        if not self._future.done():
            await curio.traps._future_wait(self._future)
        return self._future.result()

    async def exception(self):
        if not self._future.done():
            await curio.traps._future_wait(self._future)
        return self._future.exception()
