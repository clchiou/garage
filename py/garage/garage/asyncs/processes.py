__all__ = [
    'process',
]

import asyncio
import functools

from garage import asserts


class ProcessExit(Exception):
    pass


def process(coro_func=None, *, loop=None):
    """Decorator to mark processes."""
    if coro_func is None:
        return functools.partial(process, loop=loop)
    # NOTE: A coroutine object is not a coroutine function!
    asserts.precond(not asyncio.iscoroutine(coro_func))
    return Process(coro_func, loop=loop)


class Process:
    """A process is an asyncio.Task plus a `stop` future object, and
       I find this much more easier to work with than Task.cancel().
    """

    def __init__(self, coro_func, *, loop=None):
        self.coro_func = coro_func
        self.loop = loop

    def __call__(self, *args, **kwargs):
        stop_flag = asyncio.Event(loop=self.loop)
        exit_fut = asyncio.ensure_future(exit(stop_flag), loop=self.loop)
        task = asyncio.ensure_future(
            self.coro_func(exit_fut, *args, **kwargs),
            loop=self.loop,
        )
        task.add_done_callback(_silence_process_exit)
        task.add_done_callback(lambda fut: exit_fut.cancel())
        task.stop = stop_flag.set  # Monkey patch task.
        return task


async def exit(stop_flag):
    await stop_flag.wait()
    raise ProcessExit


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
