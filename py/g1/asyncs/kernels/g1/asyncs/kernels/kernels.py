__all__ = [
    'Kernel',
]

import collections
import functools
import logging
import os
import threading
import time

from g1.bases import timers
from g1.bases.assertions import ASSERT

from . import blockers
from . import contexts
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
    ],
)


class Kernel:

    def __init__(self, *, owner=None, sanity_check_frequency=10):

        self._owner = owner or threading.get_ident()

        self._num_ticks = 0
        self._sanity_check_frequency = sanity_check_frequency

        # Tasks are juggled among these collections.
        self._num_tasks = 0
        self._ready_tasks = collections.deque()
        self._task_completion_blocker = blockers.TaskCompletionBlocker()
        self._fd_blocker = blockers.DictBlocker()
        self._sleep_blocker = blockers.TimeoutBlocker()
        self._generic_blocker = blockers.DictBlocker()
        self._forever_blocker = blockers.ForeverBlocker()

        self._generic_blocker_lock = threading.Lock()

        # Track tasks that are going to raise at the next trap point
        # due to ``cancel``, ``timeout_after``, etc.  I call them
        # **disrupter** because they "disrupt" blocking traps.
        self._to_raise = {}
        self._timeout_after_blocker = blockers.TimeoutBlocker()

        self._poller = pollers.Epoll()

        self._nudger = Nudger()
        self._nudger.register_to(self._poller)

        self._blocking_trap_handlers = {
            traps.Traps.BLOCK: self._block,
            traps.Traps.JOIN: self._join,
            traps.Traps.POLL: self._poll,
            traps.Traps.SLEEP: self._sleep,
        }

    def get_stats(self):
        """Return internal stats.

        This method is not thread-safe.
        """
        return KernelStats(
            num_ticks=self._num_ticks,
            num_tasks=self._num_tasks,
            num_ready=len(self._ready_tasks),
            num_join=len(self._task_completion_blocker),
            num_poll=len(self._fd_blocker),
            num_sleep=len(self._sleep_blocker),
            num_blocked=(
                len(self._generic_blocker) + len(self._forever_blocker)
            ),
            num_to_raise=len(self._to_raise),
            num_timeout=len(self._timeout_after_blocker),
        )

    def __repr__(self):
        return '<%s at %#x: %r>' % (
            self.__class__.__qualname__,
            id(self),
            self.get_stats(),
        )

    def close(self):
        self._assert_owner()
        stats = self.get_stats()
        if any(v for n, v in stats._asdict().items() if n != 'num_ticks'):
            LOG.warning('kernel has uncompleted tasks: %r', self)
        self._poller.close()
        self._nudger.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _assert_owner(self):
        """Assert that the calling thread is the owner."""
        ASSERT.equal(threading.get_ident(), self._owner)

    def _sanity_check(self):
        with self._generic_blocker_lock:
            expect_num_tasks = self._num_tasks
            actual_num_tasks = sum(
                map(
                    len,
                    (
                        self._ready_tasks,
                        self._task_completion_blocker,
                        self._fd_blocker,
                        self._sleep_blocker,
                        self._generic_blocker,
                        self._forever_blocker,
                    ),
                )
            )
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
        self._assert_owner()
        main_task = self.spawn(awaitable) if awaitable else None
        run_timer = timers.make(timeout)
        while self._num_tasks > 0:
            # Do sanity check every ``_sanity_check_frequency`` ticks.
            if self._num_ticks % self._sanity_check_frequency == 0:
                self._sanity_check()
            self._num_ticks += 1
            # Run all ready tasks.
            while self._ready_tasks:
                completed_task = self._run_one_ready_task()
                if completed_task and completed_task is main_task:
                    # Return the result eagerly.  If you want to run all
                    # remaining tasks through completion, just call
                    # ``run`` again with no arguments.
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
                for fd, events in self._poller.poll(poll_timeout):
                    if self._nudger.is_nudged(fd, events):
                        self._nudger.ack()
                    else:
                        self._poller.unregister(fd)
                        self._trap_return(self._fd_blocker, fd, events)
                # Handle any task timeout.
                now = time.monotonic()
                self._trap_return(self._sleep_blocker, now, None)
                self._timeout_after_on_completion(now)
            # Break if ``run`` times out.
            if run_timer.is_expired():
                raise errors.Timeout

    def _run_one_ready_task(self):

        task, trap_result, trap_exception = self._ready_tasks.popleft()

        override = self._to_raise.pop(task, None)
        if override:
            trap_result = None
            trap_exception = override

        with contexts.setting_current_task(task):
            trap = task.tick(trap_result, trap_exception)

        if trap is None:
            ASSERT.true(task.is_completed())
            self._trap_return(self._task_completion_blocker, task, None)
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
    # Blocking traps.
    #

    def _block(self, task, trap):
        ASSERT.is_(trap.kind, traps.Traps.BLOCK)
        with self._generic_blocker_lock:
            self._generic_blocker.block(trap.source, task)
        if trap.post_block_callback:
            trap.post_block_callback()

    def _join(self, task, trap):
        ASSERT.is_(trap.kind, traps.Traps.JOIN)
        ASSERT.is_not(trap.task, task)  # You can't join yourself.
        if trap.task.is_completed():
            self._ready_tasks.append(TaskReady(task, None, None))
        else:
            self._task_completion_blocker.block(trap.task, task)

    def _poll(self, task, trap):
        ASSERT.is_(trap.kind, traps.Traps.POLL)
        self._poller.register(trap.fd, trap.events)
        self._fd_blocker.block(trap.fd, task)

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

    def nudge(self):
        # Do NOT ``_assert_owner`` because this may be called from
        # another thread.
        self._nudger.nudge()

    def get_all_tasks(self):
        """Return a list of all tasks.

        This method is not thread-safe, but should be useful for
        debugging.
        """
        all_tasks = []
        try:
            all_tasks.append(contexts.get_current_task())
        except LookupError:
            pass
        all_tasks.extend(task_ready.task for task_ready in self._ready_tasks)
        for task_collection in (
            self._task_completion_blocker,
            self._fd_blocker,
            self._sleep_blocker,
            self._generic_blocker,
            self._forever_blocker,
        ):
            all_tasks.extend(task_collection)
        ASSERT.equal(len(all_tasks), self._num_tasks)
        return all_tasks

    def spawn(self, awaitable):
        """Spawn a new task onto the kernel."""
        self._assert_owner()
        if tasks.Task.is_coroutine(awaitable):
            coroutine = awaitable
        else:
            coroutine = awaitable()
        task = tasks.Task(coroutine)
        self._ready_tasks.append(TaskReady(task, None, None))
        self._num_tasks += 1
        return task

    def close_fd(self, fd):
        self._assert_owner()
        self._poller.close_fd(fd)

    def unblock(self, source):
        """Unblock tasks blocked by ``source``.

        This also nudges the kernel.
        """
        # Do NOT ``_assert_owner`` because this may be called from
        # another thread.
        with self._generic_blocker_lock:
            self._trap_return(self._generic_blocker, source, None)
        self.nudge()

    def cancel(self, task):
        """Cancel the task.

        This is a no-op is task has been completed.
        """
        self._assert_owner()
        if not task.is_completed():
            self._disrupt(task, errors.TaskCancellation)

    def timeout_after(self, task, duration):
        self._assert_owner()
        if duration is None:
            return lambda: None
        if duration <= 0:
            raise errors.Timeout
        self._timeout_after_blocker.block(time.monotonic() + duration, task)
        return functools.partial(self._timeout_after_blocker.cancel, task)

    def _timeout_after_on_completion(self, now):
        for task in self._timeout_after_blocker.unblock(now):
            self._disrupt(task, errors.Timeout)

    #
    # Internal helpers.
    #

    def _disrupt(self, task, exc):
        """Raise ``exc`` in, and maybe unblock, the given ``task``."""

        # NOTE: This method has to check **all** blockers to unblock the
        # given ``task``.

        self._to_raise[task] = exc

        fd = self._fd_blocker.cancel(task)
        if fd is not None:
            self._poller.unregister(fd)
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

    def _trap_return(self, blocker, source, retval):
        for task in blocker.unblock(source):
            self._ready_tasks.append(TaskReady(task, retval, None))


class Nudger:

    def __init__(self):
        # Or should we use (Linux-specific) eventfd?
        self._r, self._w = os.pipe()
        os.set_blocking(self._r, False)
        os.set_blocking(self._w, False)

    def register_to(self, poller):
        poller.register(self._r, pollers.Epoll.READ)

    def nudge(self):
        try:
            os.write(self._w, b'\x00')
        except BlockingIOError:
            pass

    def is_nudged(self, fd, _):
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
