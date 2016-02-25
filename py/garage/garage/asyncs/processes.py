__all__ = [
    'process',
]

import asyncio
import functools

from garage import asserts

from . import queues


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
        coro = coro_func(inbox, *args, **kwargs)
        if closed_as_normal_exit:
            coro = _ignore_closed(coro)
        self.task = loop.create_task(coro)
        self.task.add_done_callback(lambda _: inbox.close(graceful=False))
        self.inbox = inbox


async def _ignore_closed(coro):
    try:
        await coro
    except queues.Closed:
        pass
