__all__ = [
    'ProcessOwner',
    'process',
]

import asyncio

from garage import asserts

from .futures import TaskOwner


# Inherit from BaseException so that `except Exception` won't catch it.
class ProcessExit(BaseException):
    pass


class process:
    """Decorate processes.

       A process is an asyncio.Task plus a `stop` future object, and
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
        proc = Process(self.coro_func(exit, *args, **kwargs), loop=loop)
        proc.add_done_callback(lambda _: exit.cancel())
        def stop():
            if not exit.cancelled():
                exit.set_exception(ProcessExit)
        proc.stop = stop
        return proc


class Process(asyncio.Task):

    # HACK: Prevent ProcessExit from bubbling up.
    def _step(self, exc=None):
        try:
            return super()._step(exc=exc)
        except ProcessExit:
            pass

    # HACK: Rewrite Task._step().
    def _wakeup(self, future):
        try:
            future.result()
        except (Exception, ProcessExit) as exc:
            self._step(exc)
        else:
            self._step()
        self = None

    # HACK: Silence ProcessExit.
    def set_exception(self, exc):
        if isinstance(exc, ProcessExit) or exc is ProcessExit:
            self.set_result(None)
        else:
            super().set_exception(exc)


class ProcessOwner(TaskOwner):

    def __init__(self):
        super().__init__()
        self.proc = None

    async def __aexit__(self, *exc_info):
        if self.proc:
            self.proc.stop()
        self.proc = None
        return await super().__aexit__(*exc_info)

    async def disown(self):
        if self.proc:
            self.proc.stop()
        self.proc = None
        return await super().disown()

    def own(self, proc):
        asserts.precond(isinstance(proc, Process))
        asserts.precond(self.proc is None)
        self.proc = proc
        return super().own(proc)
