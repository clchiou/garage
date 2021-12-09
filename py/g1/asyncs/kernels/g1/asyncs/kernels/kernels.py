__all__ = [
    'Kernel',
]

import collections
import contextlib
import errno
import functools
import inspect
import logging
import os
import sys
import threading
import time
import weakref

from g1.bases import classes
from g1.bases import timers
from g1.bases.assertions import ASSERT

from . import blockers
from . import errors
from . import pollers
from . import tasks
from . import traps

LOG = logging.getLogger(__name__)

TaskReady = collections.namedtuple(
    'TaskReady',
    'task trap_result trap_exception',
)

KernelStats = collections.namedtuple(
    'KernelStats',
    [
        'num_ticks',
        'num_tasks',
        'num_ready',
        # Blocking trap stats.
        'num_join',
        'num_poll',
        'num_sleep',
        'num_blocked',
        # Disrupter stats.
        'num_to_raise',
        'num_timeout',
        # Async generators.
        'num_async_generators',
    ],
)


class Kernel:

    def __init__(self, *, owner=None, sanity_check_frequency=100):

        self._owner = owner or threading.get_ident()

        self._closed = False

        self._num_ticks = 0
        self._sanity_check_frequency = sanity_check_frequency

        # Tasks are juggled among these collections.
        self._num_tasks = 0
        self._current_task = None
        self._ready_tasks = collections.deque()
        self._task_completion_blocker = blockers.TaskCompletionBlocker()
        self._read_blocker = blockers.DictBlocker()
        self._write_blocker = blockers.DictBlocker()
        self._sleep_blocker = blockers.TimeoutBlocker()
        self._generic_blocker = blockers.DictBlocker()
        self._forever_blocker = blockers.ForeverBlocker()

        self._async_generators = weakref.WeakSet()

        # Track tasks that are going to raise at the next trap point
        # due to ``cancel``, ``timeout_after``, etc.  I call them
        # **disrupter** because they "disrupt" blocking traps.
        self._to_raise = {}
        self._timeout_after_blocker = blockers.TimeoutBlocker()

        self._poller = pollers.Epoll()

        self._callbacks_lock = threading.Lock()
        self._callbacks = collections.deque()
        self._nudger = Nudger()
        self._nudger.register_to(self._poller)

        self._blocking_trap_handlers = {
            traps.Traps.BLOCK: self._block,
            traps.Traps.JOIN: self._join,
            traps.Traps.POLL: self._poll,
            traps.Traps.SLEEP: self._sleep,
        }

    def get_stats(self):
        """Return internal stats."""
        return KernelStats(
            num_ticks=self._num_ticks,
            num_tasks=self._num_tasks,
            num_ready=len(self._ready_tasks),
            num_join=len(self._task_completion_blocker),
            num_poll=len(self._read_blocker) + len(self._write_blocker),
            num_sleep=len(self._sleep_blocker),
            num_blocked=(
                len(self._generic_blocker) + len(self._forever_blocker)
            ),
            num_to_raise=len(self._to_raise),
            num_timeout=len(self._timeout_after_blocker),
            num_async_generators=len(self._async_generators),
        )

    __repr__ = classes.make_repr(
        '{stats!r}',
        stats=lambda self: self.get_stats(),
    )

    def close(self):
        self._assert_owner()
        if self._closed:
            return

        if self._async_generators:
            LOG.warning(
                'close: num non-finalized async generators: %d',
                len(self._async_generators),
            )
            for async_generator in self._async_generators:
                self._close_async_generator(async_generator)

        for task in self.get_all_tasks():
            if not task.is_completed():
                task.abort()

        self._poller.close()
        self._nudger.close()
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _assert_owner(self):
        """Assert that the calling thread is the owner."""
        ASSERT.equal(threading.get_ident(), self._owner)

    def _is_owner(self):
        return threading.get_ident() == self._owner

    def _sanity_check(self):
        expect_num_tasks = self._num_tasks
        actual_num_tasks = sum(
            map(
                len,
                (
                    self._ready_tasks,
                    self._task_completion_blocker,
                    self._read_blocker,
                    self._write_blocker,
                    self._sleep_blocker,
                    self._generic_blocker,
                    self._forever_blocker,
                ),
            )
        )
        if self._current_task:
            actual_num_tasks += 1
        ASSERT(
            expect_num_tasks >= 0 and expect_num_tasks == actual_num_tasks,
            'sanity check fail: {!r}',
            self,
        )

    def run(self, awaitable=None, timeout=None):
        """Run spawned tasks through completion.

        If ``awaitable`` is not ``None``, a task is spawned for it, and
        when the task completes, ``run`` returns its result.

        If ``timeout`` is non-positive, ``run`` is guarantee to iterate
        exactly once.
        """
        ASSERT.false(self._closed)
        self._assert_owner()
        ASSERT.none(self._current_task)  # Disallow recursive calls.

        main_task = self.spawn(awaitable) if awaitable else None
        run_timer = timers.make(timeout)

        while self._num_tasks > 0:

            # Do sanity check every ``_sanity_check_frequency`` ticks.
            if self._num_ticks % self._sanity_check_frequency == 0:
                self._sanity_check()
            self._num_ticks += 1

            # Fire callbacks posted by other threads.
            with self._callbacks_lock:
                callbacks, self._callbacks = \
                    self._callbacks, collections.deque()
            for callback in callbacks:
                callback()
            del callbacks

            # Run all ready tasks.
            with self._managing_async_generators():
                while self._ready_tasks:
                    completed_task = self._run_one_ready_task()
                    if completed_task and completed_task is main_task:
                        # Return the result eagerly.  If you want to run
                        # all remaining tasks through completion, just
                        # call ``run`` again with no arguments.
                        return completed_task.get_result_nonblocking()

            if self._num_tasks > 0:
                # Poll I/O.
                now = time.monotonic()
                poll_timeout = min(
                    run_timer.get_timeout(),
                    self._sleep_blocker.get_min_timeout(now),
                    self._timeout_after_blocker.get_min_timeout(now),
                    key=timers.timeout_to_key,
                )
                can_read, can_write = self._poller.poll(poll_timeout)
                for fd in can_read:
                    if self._nudger.is_nudged(fd):
                        self._nudger.ack()
                    else:
                        self._trap_return(self._read_blocker, fd)
                for fd in can_write:
                    self._trap_return(self._write_blocker, fd)

                # Handle any task timeout.
                now = time.monotonic()
                self._trap_return(self._sleep_blocker, now)
                self._timeout_after_on_completion(now)

            # Break if ``run`` times out.
            if run_timer.is_expired():
                raise errors.KernelTimeout

    def _run_one_ready_task(self):

        task, trap_result, trap_exception = self._ready_tasks.popleft()

        override = self._to_raise.pop(task, None)
        if override is not None:
            trap_result = None
            trap_exception = override

        self._current_task = task
        try:
            trap = task.tick(trap_result, trap_exception)
        finally:
            self._current_task = None

        if trap is None:
            ASSERT.true(task.is_completed())
            self._trap_return(self._task_completion_blocker, task)
            # Clear disrupter.
            self._to_raise.pop(task, None)
            self._timeout_after_blocker.cancel(task)
            self._num_tasks -= 1
            return task

        ASSERT.false(task.is_completed())
        override = self._to_raise.pop(task, None)
        if override:
            self._ready_tasks.append(TaskReady(task, None, override))
        else:
            handler = self._blocking_trap_handlers[trap.kind]
            try:
                handler(task, trap)
            except Exception as exc:
                self._ready_tasks.append(TaskReady(task, None, exc))

        return None

    #
    # Async generator management.
    #

    @contextlib.contextmanager
    def _managing_async_generators(self):
        original_hooks = sys.get_asyncgen_hooks()
        sys.set_asyncgen_hooks(
            firstiter=self._async_generator_firstiter_hook,
            finalizer=self._async_generator_finalizer_hook,
        )
        try:
            yield
        finally:
            sys.set_asyncgen_hooks(*original_hooks)

    def _async_generator_firstiter_hook(self, async_generator):
        self._async_generators.add(async_generator)

    def _async_generator_finalizer_hook(self, async_generator):
        self._async_generators.discard(async_generator)
        self._close_async_generator(async_generator)

    @staticmethod
    def _close_async_generator(async_generator):
        closer = async_generator.aclose()
        try:
            closer.send(None)
        except RuntimeError as exc:
            LOG.warning('%s: %r', exc, async_generator)
        except StopIteration:
            pass
        finally:
            closer.close()

    #
    # Blocking traps.
    #

    def _block(self, task, trap):
        ASSERT.is_(trap.kind, traps.Traps.BLOCK)
        self._generic_blocker.block(trap.source, task)
        if trap.post_block_callback:
            trap.post_block_callback()

    def _join(self, task, trap):
        ASSERT.is_(trap.kind, traps.Traps.JOIN)
        ASSERT.is_(trap.task._kernel, self)
        ASSERT.is_not(trap.task, task)  # You can't join yourself.
        if trap.task.is_completed():
            self._ready_tasks.append(TaskReady(task, None, None))
        else:
            self._task_completion_blocker.block(trap.task, task)

    def _poll(self, task, trap):
        ASSERT.is_(trap.kind, traps.Traps.POLL)
        if trap.events is pollers.Polls.READ:
            self._read_blocker.block(trap.fd, task)
        else:
            ASSERT.is_(trap.events, pollers.Polls.WRITE)
            self._write_blocker.block(trap.fd, task)

    def _sleep(self, task, trap):
        ASSERT.is_(trap.kind, traps.Traps.SLEEP)
        if trap.duration is None:
            self._forever_blocker.block(None, task)
        elif trap.duration <= 0:
            self._ready_tasks.append(TaskReady(task, None, None))
        else:
            self._sleep_blocker.block(time.monotonic() + trap.duration, task)

    #
    # Non-blocking traps.
    #

    def get_current_task(self):
        return self._current_task

    def get_all_tasks(self):
        """Return a list of all tasks (useful for debugging)."""
        self._assert_owner()
        all_tasks = []
        if self._current_task:
            all_tasks.append(self._current_task)
        all_tasks.extend(task_ready.task for task_ready in self._ready_tasks)
        for task_collection in (
            self._task_completion_blocker,
            self._read_blocker,
            self._write_blocker,
            self._sleep_blocker,
            self._generic_blocker,
            self._forever_blocker,
        ):
            all_tasks.extend(task_collection)
        ASSERT.equal(len(all_tasks), self._num_tasks)
        return all_tasks

    def spawn(self, awaitable):
        """Spawn a new task onto the kernel."""
        ASSERT.false(self._closed)
        self._assert_owner()
        if tasks.Task.is_coroutine(awaitable):
            coroutine = awaitable
        elif inspect.isawaitable(awaitable):
            coroutine = awaitable.__await__()
        else:
            coroutine = awaitable()
        task = tasks.Task(self, coroutine)
        self._ready_tasks.append(TaskReady(task, None, None))
        self._num_tasks += 1
        return task

    def notify_open(self, fd):
        ASSERT.false(self._closed)
        self._assert_owner()
        self._poller.notify_open(fd)

    def unblock(self, source):
        """Unblock tasks blocked by ``source``."""
        ASSERT.false(self._closed)
        self._assert_owner()
        self._trap_return(self._generic_blocker, source)

    def cancel(self, task):
        """Cancel the task.

        This is a no-op is task has been completed.
        """
        ASSERT.false(self._closed)
        self._assert_owner()
        ASSERT.is_(task._kernel, self)
        if not task.is_completed():
            self._disrupt(task, errors.TaskCancellation)

    def timeout_after(self, task, duration):
        ASSERT.false(self._closed)
        self._assert_owner()
        ASSERT.is_(task._kernel, self)
        if duration is None:
            return lambda: None
        # Even if duration <= 0, the kernel should raise ``Timeout`` at
        # the next blocking trap for consistency (so, don't raise here).
        self._timeout_after_blocker.block(time.monotonic() + duration, task)
        return functools.partial(self._timeout_after_blocker.cancel, task)

    def _timeout_after_on_completion(self, now):
        for task in self._timeout_after_blocker.unblock(now):
            self._disrupt(task, errors.Timeout)

    #
    # Multi-threading interface.
    #

    def post_callback(self, callback):
        ASSERT.false(self._closed)
        with self._callbacks_lock:
            self._callbacks.append(callback)
        self._nudger.nudge()

    def notify_close(self, fd):
        ASSERT.false(self._closed)
        self._poller.notify_close(fd)
        if not self._is_owner():
            self._nudger.nudge()

    #
    # Internal helpers.
    #

    def _disrupt(self, task, exc):
        """Raise ``exc`` in, and maybe unblock, the given ``task``."""

        # NOTE: This method has to check **all** blockers to unblock the
        # given ``task``.

        self._to_raise[task] = exc

        for blocker in (self._read_blocker, self._write_blocker):
            fd = blocker.cancel(task)
            if fd is not None:
                # We do not have to unregister fd here because we are
                # using edge-trigger.
                self._ready_tasks.append(TaskReady(task, None, None))
                return

        is_unblocked = (
            self._task_completion_blocker.cancel(task)
            or self._sleep_blocker.cancel(task)
            or self._generic_blocker.cancel(task)
            or self._forever_blocker.cancel(task)
        )
        if is_unblocked:
            self._ready_tasks.append(TaskReady(task, None, None))
            return

    def _trap_return(self, blocker, source):
        for task in blocker.unblock(source):
            self._ready_tasks.append(TaskReady(task, None, None))


class Nudger:

    def __init__(self):
        # Or should we use (Linux-specific) eventfd?
        self._r, self._w = os.pipe()
        os.set_blocking(self._r, False)
        os.set_blocking(self._w, False)

    def register_to(self, poller):
        poller.notify_open(self._r)
        # NOTE: We skip `notify_close` on in `close` below since Nudger
        # is closed when the Kernel is closing.

    def nudge(self):
        try:
            os.write(self._w, b'\x00')
        except BlockingIOError:
            pass
        except OSError as exc:
            if exc.errno == errno.EBADF:
                # The kernel has closed the nudger, but another thread
                # still tries to nudge the kernel.  This usually happens
                # during program exit
                LOG.warning('nudger was closed')
            else:
                raise

    def is_nudged(self, fd):
        return self._r == fd

    def ack(self):
        try:
            # Drain the pipe.
            while os.read(self._r, 4096):
                pass
        except BlockingIOError:
            pass

    def close(self):
        os.close(self._r)
        os.close(self._w)
