__all__ = [
    'TaskCancelled',
    'TaskStack',
    'spawn',
]

from collections import deque
from functools import partial

import curio


class TaskCancelled(BaseException):
    pass


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

    def decorated(throw, type_, *args):
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

    task = await curio.spawn(coro, **kwargs)
    task._throw = partial(decorated, task._throw)
    return task


class TaskStack:
    """A class that is similar to ExitStack but is specific for Task and
       cancels all tasks on exit.

       You may use this class to propagate task cancellation from parent
       task to child tasks.

       (By default, use asyncs.spawn rather than curio.spawn.)
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
