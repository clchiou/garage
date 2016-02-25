__all__ = [
    'ensure_process',
]

import asyncio
import functools

from garage import asserts

from . import queues


def ensure_process(coro_func=None, make_queue=None, loop=None):
    """Wrap a coroutine function or a function that returns coroutine to
       return process when called.
    """

    if coro_func is None:
        return functools.partial(
            ensure_process, make_queue=make_queue, loop=loop)

    # NOTE: A coroutine object is not a coroutine function!
    asserts.precond(not asyncio.iscoroutine(coro_func))

    @functools.wraps(coro_func)
    def make_process(*args, **kwargs):
        return Process(
            make_process.coro_func, args, kwargs,
            make_queue=make_process.make_queue,
            loop=make_process.loop,
        )

    make_process.coro_func = coro_func
    make_process.make_queue = make_queue
    make_process.loop = loop

    return make_process


class Process:

    def __init__(self, coro_func, args, kwargs, *, make_queue=None, loop=None):
        loop = loop or asyncio.get_event_loop()
        self.inbox = make_queue() if make_queue else queues.Queue(loop=loop)
        self.linked_procs = set()
        # Schedule the task...
        self.task = loop.create_task(
            self._run_coro(coro_func(self.inbox, *args, **kwargs)))

    def __await__(self):
        return self.task.__await__()

    def link(self, proc):
        asserts.precond(not self.inbox.is_closed() and
                        not proc.inbox.is_closed())
        self.linked_procs.add(proc)
        proc.linked_procs.add(self)

    async def send(self, message, block=True):
        await self.inbox.put(message, block=block)

    async def _run_coro(self, coro):
        try:
            await coro
        except queues.Closed:
            pass
        finally:
            self.inbox.close(graceful=False)
            # Stop linked processes as soon as possible.
            for proc in self.linked_procs:
                await proc.shutdown(graceful=False)

    async def shutdown(self, graceful=True, recursive=False):
        # Exit if inbox is closed to prevent circular calls.
        if self.inbox.is_closed():
            return
        self.inbox.close(graceful=graceful)
        if recursive:
            for proc in self.linked_procs:
                await proc.shutdown(graceful=graceful, recursive=recursive)
