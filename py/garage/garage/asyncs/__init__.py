__all__ = [
    'Event',
    'TaskCancelled',
    'TaskSet',
    'TaskStack',
    'cancelling',
    'select',
    'spawn',
    # HACK!
    'close_socket_and_wakeup_task',
]

from collections import OrderedDict, deque
from functools import partial
import inspect

import curio
import curio.io
import curio.traps

from garage.assertions import ASSERT

from . import queues
from .base import Event  # Create an alias to base.Event


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
    # I assume curio doesn't pass any other args
    ASSERT(not args, 'not expect args for throw(): %r', args)
    if type_ is curio.TaskCancelled or type(type_) is curio.TaskCancelled:
        # Raise asyncs.TaskCancelled in task's coroutine but raise
        # curio.TaskCancelled in the curio main loop.
        try:
            return throw(TaskCancelled)
        except TaskCancelled as e:
            raise type_ from e
    else:
        return throw(type_, *args)


class cancelling:

    @classmethod
    async def spawn(cls, coro, *, spawn=spawn, **kwargs):
        return cls(await spawn(coro, **kwargs))

    def __init__(self, task):
        self.task = task

    async def __aenter__(self):
        return self.task

    async def __aexit__(self, *_):
        await self.task.cancel()


async def select(cases, *, spawn=spawn):
    """Wait on a list of coroutine or task and return the first done.

       The cases parameter could be either a dict-like with a keys()
       method or an iterable object.  If it's a dict-like object, the
       keys are either a coroutine or a task.

       The advantage of select() over curio.TaskGroup is that it accepts
       coroutines and spawns new tasks for those coroutines so that they
       may be waited in parallel.  Also select() will clean up itself by
       cancelling those internally-spawned tasks on its way out.
    """
    async with TaskStack(spawn=spawn) as stack:
        dict_like = hasattr(cases, 'keys')
        tasks = {}
        for coro_or_task in cases:
            if inspect.iscoroutine(coro_or_task):
                task = await stack.spawn(coro_or_task)
            else:
                task = coro_or_task
            tasks[task] = dict_like and cases[coro_or_task]
        # XXX A Task object cannot belong to more than one TaskGroup; as
        # a result, if one of the task in the `cases` is spawning from a
        # TaskGroup, curio.TaskGroup() will raise an AssertionError.
        done_task = await curio.TaskGroup(tasks).next_done()
        if dict_like:
            return done_task, tasks[done_task]
        else:
            return done_task


class TaskSet:
    """Similar to curio.TaskGroup, but use asyncs.spawn by default."""

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

    class TaskGroupAdapter:

        def __init__(self, task_set):
            self.__task_set = task_set

        # Callback from curio.Task
        async def _task_done(self, task):
            self.__task_set._on_task_done(task)

        # Callback from curio.Task
        def _task_discard(self, task):
            pass  # Nothing here

    def __init__(self, *, spawn=spawn):
        self._pending_tasks = OrderedDict()  # For implementing OrderedSet
        self._done_tasks = queues.Queue()
        self._graceful_exit = False
        self._spawn = spawn

    def ignore_done_tasks(self):
        """Do not track done tasks."""
        self._done_tasks.close()

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
        ASSERT(not self._graceful_exit, '%s is closing', self)
        task = await self._spawn(coro, **kwargs)
        ASSERT.false(task._taskgroup)
        ASSERT.false(task._ignore_result)
        self._pending_tasks[task] = None  # Dummy value
        task._taskgroup = self.TaskGroupAdapter(self)
        return task

    def _on_task_done(self, task):
        if self._pending_tasks:
            self._pending_tasks.pop(task)
        # When we are aborting (bypassing graceful_exit()), there could
        # be tasks being done after we closed the _done_tasks queue (for
        # this to happen, we only need two tasks being done after
        # __aexit__ returns, and then the first task's _on_task_done closes
        # the _done_tasks queue (because _pending_tasks is None) and the
        # second task's _on_task_done sees a closed _done_tasks queue)
        if not self._done_tasks.is_closed():
            # Call put_nowait() so that we won't be blocked by put()
            # (is being blocked here a problem?)
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

       Note: curio.TaskGroup does not cancel tasks in reverse order but
       TaskStack does.
    """

    def __init__(self, *, spawn=spawn):
        self._tasks = None
        self._callbacks = None
        self._spawn = spawn

    async def __aenter__(self):
        ASSERT.none(self._callbacks)
        self._tasks = deque()
        self._callbacks = deque()
        return self

    async def __aexit__(self, *_):
        ASSERT.not_none(self._callbacks)
        self._tasks = None
        callbacks, self._callbacks = self._callbacks, None
        for is_async, func, args, kwargs in reversed(callbacks):
            if is_async:
                await func(*args, **kwargs)
            else:
                func(*args, **kwargs)

    def __iter__(self):
        ASSERT.not_none(self._tasks)
        yield from self._tasks

    async def wait_any(self):
        ASSERT.not_none(self._tasks)
        return await curio.TaskGroup(self._tasks).next_done()

    async def spawn(self, coro, **kwargs):
        """Spawn a new task and push it onto stack."""
        ASSERT.not_none(self._callbacks)
        task = await self._spawn(coro, **kwargs)
        self._tasks.append(task)
        self.callback(task.cancel)
        return task

    def callback(self, func, *args, **kwargs):
        """Add asynchronous callback."""
        ASSERT.not_none(self._callbacks)
        self._callbacks.append((True, func, args, kwargs))

    def sync_callback(self, func, *args, **kwargs):
        """Add synchronous callback."""
        ASSERT.not_none(self._callbacks)
        self._callbacks.append((False, func, args, kwargs))


async def close_socket_and_wakeup_task(socket):
    """Close a socket and wake up any task blocked on it.

    This is a hack to workaround the issue that when a file descriptor
    is closed, any task blocked on it will not be waked up, and thus
    will be blocked forever.

    NOTE: There will be at most one task blocked on a file descriptor.
    """
    ASSERT.type_of(socket, curio.io.Socket)

    if not socket._socket:
        return  # It's closed already.

    kernel = await curio.traps._get_kernel()

    def mark_ready(task):
        kernel._ready.append(task)
        task.next_value = None
        task.next_exc = None
        task.state = 'READY'
        task.cancel_func = None

    # Wake up tasks and unregister the file from event loop.
    fileno = socket._fileno
    try:
        key = kernel._selector.get_key(fileno)
        rtask, wtask = key.data
        if rtask:
            mark_ready(rtask)
        if wtask:
            mark_ready(wtask)
        kernel._selector.unregister(fileno)
    except KeyError:
        pass

    await socket.close()
