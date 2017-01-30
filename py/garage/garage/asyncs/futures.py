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
    'FutureError',
    'Future',
]

import enum

import curio


class CancelledError(Exception):
    """The Future was cancelled."""


# This error class is for working around an issue below.
# TODO: Remove this class if we could fix the issue.
class FutureError(Exception):
    """Promise calls set_exception()."""


# The API is designed that you most likely don't need to check specific
# Future.state.
class State(enum.Enum):
    PENDING = 'PENDING'
    CANCELLED = 'CANCELLED'
    FINISHED = 'FINISHED'


class Future:

    # You should not construct Promise objects directly, and should call
    # Future.make_promise to get Promise objects.
    class Promise:

        def __init__(self, future):
            self._future = future

        # It's usually a good idea that you check whether the job has
        # been cancelled before starting it.
        def is_cancelled(self):
            return self._future.state is State.CANCELLED

        async def _set(self, result, exception):
            if self._future.state is State.CANCELLED:
                return
            elif self._future.state is State.FINISHED:
                raise AssertionError(
                    'Future has been marked FINISHED: %r' % self._future)
            else:  # self._future.state is State.PENDING
                assert not self._future._end.is_set()
                self._future._result = result
                self._future._exception = exception
                self._future.state = State.FINISHED
                await self._future._end.set()

        async def set_result(self, result):
            await self._set(result, None)

        async def set_exception(self, exception):
            await self._set(None, exception)

    def __init__(self):
        self._end = curio.Event()  # Set when state is not PENDING
        self._result = None
        self._exception = None
        self.state = State.PENDING

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.cancel()

    def make_promise(self):
        # Future won't reference to Promise to avoid cyclic reference.
        return Future.Promise(self)

    async def cancel(self):
        """Notify the Promise holder that the Future holder is not
           interested in the result anymore.

           Return True if the future is actually cancelled.
        """
        if self.state is State.PENDING:
            self.state = State.CANCELLED
            await self._end.set()
            return True
        else:
            assert self._end.is_set()
            return False

    async def get_result(self):
        await self._end.wait()
        assert self.state is not State.PENDING
        if self.state is State.CANCELLED:
            raise CancelledError
        elif self._exception is not None:
            # I don't fully understand why, but it seems that when
            # self._exception is coming from an awaited coroutine, in
            # some cases curio.Kernel will try to re-use it in the same
            # coroutine and cause RuntimeError.  So we can't raise
            # self._exception` here, but have to wrap it in FutureError
            # exception.
            raise FutureError() from self._exception
        else:
            return self._result

    async def get_exception(self):
        await self._end.wait()
        assert self.state is not State.PENDING
        if self.state is State.CANCELLED:
            raise CancelledError
        else:
            return self._exception
