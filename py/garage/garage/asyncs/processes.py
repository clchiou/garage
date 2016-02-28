__all__ = [
    'Nudges',
    'process',
]

import asyncio
import functools
import logging

from garage import asserts

from . import queues
from .futures import awaiting


LOG = logging.getLogger(__name__)


class Nudges:
    """Nudge tasks and wait for them to exit.

       A nudge should not cancel tasks but should request tasks to exit
       cooperatively.
    """

    def __init__(self, *, timeout=None, loop=None):
        self.nudges = set()
        self.tasks = set()
        self.proc_table = {}
        self.timeout = timeout
        self.loop = loop

    def add_nudge(self, nudge):
        """Add a nudge - which is just a (coroutine) function that takes
           no argument.
        """
        self.nudges.add(nudge)
        return nudge

    def add_task(self, coro_or_task):
        """Add a task that will be waited for."""
        task = asyncio.ensure_future(coro_or_task)
        self.tasks.add(task)
        return task

    def add_proc(self, proc):
        """Add a process that will be nudged then waited for."""
        self.proc_table[proc] = (
            self.add_nudge(proc.inbox.close),
            self.add_task(proc.task),
        )
        return proc

    def remove_proc(self, proc):
        nudge, task = self.proc_table.pop(proc)
        self.nudges.remove(nudge)
        self.tasks.remove(task)

    def add_inbox(self, inbox):
        """Add a nudge through the inbox."""
        self.add_nudge(inbox.close)
        return inbox

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        for nudge in self.nudges:
            maybe_coro = nudge()
            if asyncio.iscoroutine(maybe_coro):
                await maybe_coro
        tasks = self.tasks
        while tasks:
            done, tasks = await asyncio.wait(
                tasks, timeout=self.timeout, loop=self.loop)
            for task in done:
                try:
                    await task
                except queues.Closed:
                    pass
                except Exception:
                    LOG.debug('error of %r', task, exc_info=True)


def process(coro_func=None, *, make_queue=None, loop=None):
    """Decorator to mark processes."""
    if coro_func is None:
        return functools.partial(process, make_queue=make_queue, loop=loop)
    # NOTE: A coroutine object is not a coroutine function!
    asserts.precond(not asyncio.iscoroutine(coro_func))
    return ProcessFactory(coro_func, make_queue, loop=loop)


class ProcessFactory:

    def __init__(self, coro_func, make_queue, *, loop):
        self.coro_func = coro_func
        self.closed_as_normal_exit = True
        self.make_queue = make_queue
        self.loop = loop

    def __call__(self, *args, **kwargs):
        return Process(self.coro_func, args, kwargs,
                       closed_as_normal_exit=self.closed_as_normal_exit,
                       make_queue=self.make_queue,
                       loop=self.loop)


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

    async def __aenter__(self):
        self._context_manager = awaiting(self.task, loop=self.loop)
        await self._context_manager.__aenter__()
        return self

    async def __aexit__(self, *exc_info):
        self.inbox.close()
        return await self._context_manager.__aexit__(*exc_info)


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
