__all__ = [
    'Throne',
    'process',
    'until_closed',
]

import asyncio
import functools
import logging

from garage import asserts

from . import queues
from .futures import awaiting


LOG = logging.getLogger(__name__)


class Throne:
    """A throne represents a continuous service provided by processes.
       When a process dies, a new process is (immediately) created to
       continue the service.

       The process is dead, long live the process!
    """

    def __init__(self, *, loop=None):
        self.proc = None
        self._throne = awaiting.replaceable(loop=loop)

    async def __aenter__(self):
        await self._throne.__aenter__()
        return self

    async def __aexit__(self, *exc_info):
        if self.proc:
            self.proc.inbox.close()
        return await self._throne.__aexit__(*exc_info)

    async def dethrone(self):
        """Dethrone the current process.

           This is blocking - as dethroning all kings.
        """
        asserts.precond(self.proc)
        proc, self.proc = self.proc, None
        proc.inbox.close()
        await self._throne.remove()
        return proc

    def throne(self, proc):
        """Make the new process come to the throne.

           This is non-blocking.
        """
        asserts.precond(proc)
        self._throne.set(proc.task)
        self.proc = proc
        return self.proc


def process(coro_func=None, *, make_queue=None, loop=None):
    """Decorator to mark processes."""
    if coro_func is None:
        return functools.partial(process, make_queue=make_queue, loop=loop)
    # NOTE: A coroutine object is not a coroutine function!
    asserts.precond(not asyncio.iscoroutine(coro_func))
    return ProcessFactory(coro_func, make_queue, loop=loop)


class ProcessFactory:

    def __init__(self, coro_func, make_queue, *, loop=None):
        self.coro_func = coro_func
        self.closed_as_normal_exit = True
        self.make_queue = make_queue
        self.loop = loop

    def __call__(self, *args, **kwargs):
        return self.make(args, kwargs)

    def make(self, args, kwargs, **options):
        for opt in ('closed_as_normal_exit', 'make_queue', 'loop'):
            options.setdefault(opt, getattr(self, opt))
        return Process(self.coro_func, args, kwargs, **options)


class Process:
    """A process is just a asyncio.Task with an inbox queue.

       The task is intended to be the only consumer of the inbox and so
       when the task is done, the inbox queue is closed.  If you need
       something like a shared inbox, you should create it separately.
    """

    def __init__(self, coro_func, args, kwargs, *,
                 closed_as_normal_exit=True,
                 make_queue=None,
                 loop=None):
        self.loop = loop
        inbox = make_queue() if make_queue else queues.Queue(loop=self.loop)
        # Schedule the task while avoiding circular reference - don't
        # hold `self` or `self.inbox` but just plain `inbox`.
        self.task = asyncio.ensure_future(
            coro_func(inbox, *args, **kwargs), loop=self.loop)
        self.task.add_done_callback(lambda _: inbox.close(graceful=False))
        if closed_as_normal_exit:
            self.task.add_done_callback(_silence_closed)
        self.inbox = inbox

    def stop(self, graceful=True):
        self.inbox.close(graceful=graceful)

    def __await__(self):
        return self.task.__await__()

    async def __aenter__(self):
        self._context_manager = awaiting(self.task, loop=self.loop)
        await self._context_manager.__aenter__()
        return self

    async def __aexit__(self, *exc_info):
        self.inbox.close()
        return await self._context_manager.__aexit__(*exc_info)


def until_closed(inbox, *, closed_as_normal_exit=True, loop=None):
    """Wrap inbox.until_closed() in an awaiting context manager."""
    cxtmgr = awaiting(inbox.until_closed(), cancel_on_exit=True, loop=loop)
    if closed_as_normal_exit:
        cxtmgr.silence_exc_type = queues.Closed
    return cxtmgr


def _silence_closed(future):
    #
    # Hack for silencing queues.Closed of a finished future!
    #
    # You could alternatively use a wrapper coroutine to silence the
    # queues.Closed exception, but then `repr(future)` would show the
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
    if not isinstance(future._exception, queues.Closed):
        return

    # 2. Call future.exception() to silence traceback logger.
    exc = future.exception()

    # 3. Make sure future.exception() returns future._exception;
    #    otherwise this hack wouldn't work.
    asserts.precond(exc is future._exception)

    # 4. Clear exception so that future.result() wouldn't raise.
    future._exception = None
