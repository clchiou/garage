__all__ = [
    'EachCompleted',
    'Nudges',
    'process',
]

import asyncio
import functools
import logging

from garage import asserts

from . import queues


LOG = logging.getLogger(__name__)


class EachCompleted:
    """A fancy wrapper of asyncio.wait() that takes a required and an
       optional set of futures and stops waiting after all required
       futures are done (some of the optional set futures might not be
       done yet).
    """

    def __init__(self, required, optional=(), *, timeout=None, loop=None):
        self.required = set(required)
        self.optional = set(optional)
        self.timeout = timeout
        self.loop = loop
        self._done = None

    async def __aiter__(self):
        return self

    async def __anext__(self):
        if self._done:
            return self._done.pop()
        if not self.required:
            raise StopAsyncIteration
        self._done, _ = await asyncio.wait(
            self.required | self.optional,
            timeout=self.timeout,
            loop=self.loop,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for fut in self._done:
            self.required.discard(fut)
            self.optional.discard(fut)
        return self._done.pop()


class Nudges:
    """Nudge tasks and wait for them to exit.

       A nudge should not cancel tasks but should request tasks to exit
       cooperatively.
    """

    def __init__(self, *, timeout=None, loop=None):
        self.nudges = []
        self.tasks = []
        self.timeout = timeout
        self.loop = loop

    def add_nudge(self, nudge):
        """Add a nudge - which is just a (coroutine) function that takes
           no argument.
        """
        self.nudges.append(nudge)
        return nudge

    def add_task(self, coro_or_task):
        """Add a task that will be waited for."""
        task = asyncio.ensure_future(coro_or_task)
        self.tasks.append(task)
        return task

    def add_proc(self, proc):
        """Add a process that will be nudged then waited for."""
        self.add_nudge(proc.inbox.close)
        self.add_task(proc.task)
        return proc

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
        loop = loop or asyncio.get_event_loop()
        inbox = make_queue() if make_queue else queues.Queue(loop=loop)
        # Schedule the task while avoiding circular reference - don't
        # hold `self` but `inbox`.
        self.task = loop.create_task(coro_func(inbox, *args, **kwargs))
        self.task.add_done_callback(lambda _: inbox.close(graceful=False))
        if closed_as_normal_exit:
            self.task.add_done_callback(_silence_closed)
        self.inbox = inbox


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

    # 1. Call future.exception() to silence traceback logger.
    exc = future.exception()

    # 2. Make sure future.exception() returns future._exception;
    #    otherwise this hack wouldn't work.
    asserts.precond(exc is future._exception)

    # 3. Clear exception so that future.result() wouldn't raise.
    if isinstance(future._exception, queues.Closed):
        future._exception = None
