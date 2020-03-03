"""Task management utilities."""

__all__ = [
    'Cancelled',
    'Closed',
    'CompletionQueue',
    'as_completed',
    'get_all_tasks',
    'get_current_task',
    'join_and_log_on_error',
    'joining',
    'spawn',
    'spawn_onto_stack',
]

import collections
import logging

from g1.asyncs.kernels import contexts
from g1.bases import classes

# Re-export errors.
from g1.asyncs.kernels.errors import Cancelled

from . import locks

LOG = logging.getLogger(__name__)


class Closed(Exception):
    pass


class CompletionQueue:
    """Provide queue-like interface on waiting for task completion.

    NOTE: It does not support future objects; this simplifies its
    implementation, and thus may be more efficient.
    """

    def __init__(self):
        self._gate = locks.Gate()
        self._completed = collections.deque()
        self._uncompleted = set()
        self._closed = False

    __repr__ = classes.make_repr(
        '{state} uncompleted={uncompleted} completed={completed}',
        state=lambda self: 'closed' if self._closed else 'open',
        uncompleted=lambda self: len(self._uncompleted),
        completed=lambda self: len(self._completed),
    )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, *_):
        """Reasonable default policy on joining tasks.

        * First, it will close the queue.
        * On normal exit, it will join all remaining tasks.
        * On error, it will cancel tasks before joining them.

        This is not guaranteed to fit any use case though.  On those
        cases, you will have to roll your own context manager.
        """
        tasks = self.close(graceful=False)
        if exc_type:
            for task in tasks:
                task.cancel()
        for task in tasks:
            await join_and_log_on_error(task)

    def is_closed(self):
        return self._closed

    def __bool__(self):
        return bool(self._completed) or bool(self._uncompleted)

    def __len__(self):
        return len(self._completed) + len(self._uncompleted)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.get()
        except Closed:
            raise StopAsyncIteration

    def close(self, graceful=True):
        if graceful:
            tasks = []
        else:
            tasks = list(self._completed)
            tasks.extend(self._uncompleted)
            self._completed.clear()
            self._uncompleted.clear()
        self._closed = True
        self._gate.unblock()
        return tasks

    async def get(self):
        while True:
            if self._completed:
                return self._completed.popleft()
            elif self._uncompleted or not self._closed:
                await self._gate.wait()
            else:
                raise Closed

    def put_nonblocking(self, task):
        if self._closed:
            raise Closed
        self._uncompleted.add(task)
        task.add_callback(self._on_completion)

    def spawn(self, awaitable):
        """Spawn and put task to the queue.

        This is equivalent to spawn-then-put, but is better that, if
        ``put`` will fail, no task is spawned.
        """
        if self._closed:
            raise Closed
        task = spawn(awaitable)
        try:
            self.put_nonblocking(task)
        except BaseException:
            # This should never happen...
            LOG.critical('put should never fail here: %r, %r', self, task)
            task.cancel()
            raise
        return task

    def _on_completion(self, task):
        if self._uncompleted:
            self._uncompleted.remove(task)
            self._completed.append(task)
        self._gate.unblock()


async def as_completed(tasks):
    completed = collections.deque()
    gate = locks.Gate()
    num_tasks = 0
    for task in tasks:
        task.add_callback(lambda t: (completed.append(t), gate.unblock()))
        num_tasks += 1
    while num_tasks > 0:
        while not completed:
            await gate.wait()
        yield completed.popleft()
        num_tasks -= 1


async def join_and_log_on_error(task):
    exc = await task.get_exception()
    if not exc:
        pass
    elif isinstance(exc, Cancelled):
        LOG.debug('task is cancelled: %r', task, exc_info=exc)
    else:
        LOG.error('task error: %r', task, exc_info=exc)


class joining:
    """Ensure the given task cannot outlive a scope."""

    def __init__(self, task, *, always_cancel=False, log_on_error=True):
        self._task = task
        self._always_cancel = always_cancel
        self._log_on_error = log_on_error

    async def __aenter__(self):
        return self._task

    async def __aexit__(self, exc_type, *_):
        if exc_type or self._always_cancel:
            self._task.cancel()
        if self._log_on_error:
            await join_and_log_on_error(self._task)
        else:
            await self._task.join()


def spawn(awaitable):
    return contexts.get_kernel().spawn(awaitable)


def spawn_onto_stack(awaitable, stack, **kwargs):
    task = spawn(awaitable)
    stack.push_async_exit(joining(task, **kwargs).__aexit__)
    return task


def get_all_tasks():
    # You may call this out of a kernel context.
    kernel = contexts.get_kernel(None)
    return kernel.get_all_tasks() if kernel else []


def get_current_task():
    # You may call this out of a kernel context.
    kernel = contexts.get_kernel(None)
    return kernel.get_current_task() if kernel else None
