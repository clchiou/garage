__all__ = [
    'TaskStack',
]

from collections import deque

import curio


class TaskStack:
    """A class that is similar to ExitStack but is specific for Task and
       cancels all tasks on exit.

       You may use this class to propagate task cancellation from parent
       task to child tasks.
    """

    def __init__(self):
        self._tasks = None

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
        """Call curio.spawn() to spawn a task and push it to stack."""
        assert self._tasks is not None
        task = await curio.spawn(coro, **kwargs)
        self._tasks.append(task)
        return task
