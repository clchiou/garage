__all__ = [
    'TaskCancelled',
    'TaskSet',
    'TaskStack',
    'cancel_on_exit',
    'spawn',
]

from collections import OrderedDict, deque
from functools import partial

import curio

from . import queues


class TaskCancelled(BaseException):
    pass


class cancel_on_exit:

    def __init__(self, task):
        self.task = task

    async def __aenter__(self):
        return self.task

    async def __aexit__(self, *_):
        await self.task.cancel()


async def spawn(coro, **kwargs):
    """Call curio.spawn() and patch the task object so that when it is
       cancelled, asyncs.TaskCancelled is raised inside the coroutine.

       asyncs.TaskCancelled is derived from BaseException, which has the
       benefits that the usual catch-all exception block won't catch it,
       and thus doesn't have to explicitly re-throw.  This is especially
       valuable when calling into third-party libraries that are unaware
       of and don't re-throw TaskCancelled.  For example:

       When throwing curio.TaskCancelled:
           try:
               ...
           except curio.TaskCancelled:
               # Need to explicitly re-throw due to catch-all below.
               raise
           except Exception:
               ...

       When throwing asyncs.TaskCancelled:
           try:
               ...
           except Exception:
               # No need to explicitly re-throw.
               ...
    """

    task = await curio.spawn(coro, **kwargs)
    task._send = partial(_send, task._send)
    task._throw = partial(_throw, task._throw)

    return task


def _send(send, arg):
    try:
        return send(arg)
    except TaskCancelled as e:
        raise curio.TaskCancelled from e


def _throw(throw, type_, *args):
    assert not args
    if type_ is curio.TaskCancelled or type(type_) is curio.TaskCancelled:
        # Raise asyncs.TaskCancelled in task's coroutine but raise
        # curio.TaskCancelled in the curio main loop.
        try:
            return throw(TaskCancelled)
        except TaskCancelled as e:
            raise type_ from e
    else:
        return throw(type_, *args)


class TaskSet:
    """This class is similar to curio.wait, but you may add tasks to it
       even after it starts waiting.
    """

    #
    # State transition:
    #             --> __init__()      --> OPERATING
    #   OPERATING --> graceful_exit() --> CLOSING
    #   OPERATING --> __aexit__()     --> CLOSED
    #   CLOSING   --> __aexit__()     --> CLOSED
    #
    # OPERATING == not self._graceful_exit and self._pending_tasks is not None
    # CLOSING   ==     self._graceful_exit and self._pending_tasks is not None
    # CLOSED    ==     self._graceful_exit and not self._pending_tasks
    #

    def __init__(self, *, spawn=spawn):
        self._pending_tasks = OrderedDict()  # For implementing OrderedSet
        self._done_tasks = queues.Queue()
        self._graceful_exit = False
        self._spawn = spawn

    def graceful_exit(self):
        self._graceful_exit = True
        # We may close the _done_tasks queue when it's CLOSED state
        if not self._pending_tasks:
            self._done_tasks.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.graceful_exit()
        tasks, self._pending_tasks = self._pending_tasks, None
        for task in reversed(tasks.keys()):
            await task.cancel()

    async def spawn(self, coro, **kwargs):
        if self._graceful_exit:
            raise AssertionError('%s is closing' % self)
        task = await self._spawn(coro, **kwargs)
        self._pending_tasks[task] = None  # Dummy value
        await curio.spawn(self._join_task(task))
        return task

    async def _join_task(self, task):
        try:
            await task.join()
        except Exception:
            pass
        if self._pending_tasks:
            self._pending_tasks.pop(task)
        # When we are aborting (bypassing graceful_exit()), there could
        # be tasks being done after we closed the _done_tasks queue (for
        # this to happen, we only need two tasks being done after
        # __aexit__ returns, and then the first task's _join_task closes
        # the _done_tasks queue (because _pending_tasks is None) and the
        # second task's _join_task sees a closed _done_tasks queue)
        if not self._done_tasks.is_closed():
            self._done_tasks.put_nowait(task)
        # We may close the _done_tasks queue when it's CLOSED state
        if self._graceful_exit and not self._pending_tasks:
            self._done_tasks.close()

    async def next_done(self):
        try:
            return await self._done_tasks.get()
        except queues.Closed:
            return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        next = await self.next_done()
        if next is None:
            raise StopAsyncIteration
        return next


class TaskStack:
    """A class that is similar to ExitStack but is specific for Task and
       cancels all tasks on exit.

       You may use this class to propagate task cancellation from parent
       task to child tasks.

       (By default, use asyncs.spawn rather than curio.spawn.)

       Note: curio.wait does not cancel tasks in reverse order but
       TaskStack does.
    """

    def __init__(self, *, spawn=spawn):
        self._tasks = None
        self._spawn = spawn

    async def __aenter__(self):
        assert self._tasks is None
        self._tasks = deque()
        return self

    async def __aexit__(self, *exc_info):
        assert self._tasks is not None
        tasks, self._tasks = self._tasks, None
        for task in reversed(tasks):
            await task.cancel()

    def __iter__(self):
        assert self._tasks is not None
        yield from self._tasks

    async def spawn(self, coro, **kwargs):
        """Spawn a new task and push it onto stack."""
        assert self._tasks is not None
        task = await self._spawn(coro, **kwargs)
        self._tasks.append(task)
        return task
