__all__ = [
    'process',
]

import asyncio

from garage import asserts


class ProcessExit(Exception):
    pass


class process:
    """A process is an asyncio.Task plus a `stop` future object, and
       I find this much more easier to work with than Task.cancel().
    """

    def __init__(self, coro_func):
        # NOTE: A coroutine object is not a coroutine function!
        asserts.precond(not asyncio.iscoroutine(coro_func))
        self.coro_func = coro_func

    def __call__(self, *args, **kwargs):
        return self.make(args, kwargs, loop=None)

    def make(self, args, kwargs, *, loop=None):
        exit = asyncio.Future(loop=loop)
        task = asyncio.ensure_future(
            self.coro_func(exit, *args, **kwargs), loop=loop)
        task.add_done_callback(_silence_process_exit)
        task.add_done_callback(lambda fut: exit.cancel())
        def stop():
            if not exit.cancelled():
                exit.set_exception(ProcessExit)
        task.stop = stop
        return task


def _silence_process_exit(future):
    #
    # Hack for silencing ProcessExit of a finished future!
    #
    # You could alternatively use a wrapper coroutine to silence the
    # ProcessExit exception, but then `repr(future)` would show the
    # location of the wrapper rather than the original coroutine, which
    # is quite inconvenient when debugging.
    #
    # If other callbacks (added by future.add_done_callback) is called
    # sooner than this one, they may see the not-cleared-yet exception,
    # which could be raised there :(
    #

    # 0. Check our assumption about future object internal.
    asserts.precond(hasattr(future, '_exception'))

    # 1. Don't alter states of futures that we don't want to silence.
    if not isinstance(future._exception, ProcessExit):
        return

    # 2. Call future.exception() to silence traceback logger.
    exc = future.exception()

    # 3. Make sure future.exception() returns future._exception;
    #    otherwise this hack wouldn't work.
    asserts.precond(exc is future._exception)

    # 4. Clear exception so that future.result() wouldn't raise.
    future._exception = None
