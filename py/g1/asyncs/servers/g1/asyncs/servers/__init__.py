"""Supervisor tree.

This is not a framework for, but is a somewhat opinionated design of the
supervisor tree model.  It assumes that:

* An application is a collection of server tasks, which are supervised
  by the root supervisor.

* A server task is a top-level, long-running task.  Upon receiving a
  client request, it spawns and supervises a handler task to serve the
  request.
"""

__all__ = [
    'SupervisorError',
    'supervise_handlers',
    'supervise_servers',
]

import contextlib
import logging
import signal

from g1.asyncs.bases import signals
from g1.asyncs.bases import tasks
from g1.asyncs.bases import timers

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

EXIT_SIGNUMS = (
    signal.SIGINT,
    signal.SIGTERM,
)


class SupervisorError(Exception):
    """Raise when supervisor exits non-gracefully."""


async def supervise_servers(
    server_queue,
    graceful_exit,
    grace_period,  # Unit: seconds.
):
    """Supervise server tasks.

    * If one of the server tasks exits, this supervisor will stop all
      remaining server tasks (this may or may not be done gracefully).

    * This supervisor installs a signal handler so that you may trigger
      graceful exit via signals.

    * ``server_queue`` is a ``CompletionQueue`` of the server tasks.  It
      is closed when this supervisor begins stopping server tasks.

    * ``graceful_exit`` is an event object that, once set, this
      supervisor will begin stopping servers gracefully.  Any task may
      wait on this event object to get notified on graceful exit.
    """
    async with contextlib.AsyncExitStack() as stack:
        await _ServerSupervisor(
            stack=stack,
            this_task=tasks.get_current_task(),
            server_queue=server_queue,
            graceful_exit=graceful_exit,
            grace_period=grace_period,
        ).supervise()


class _ServerSupervisor:

    def __init__(
        self,
        stack,
        this_task,
        server_queue,
        graceful_exit,
        grace_period,
    ):
        self.stack = stack
        self.this_task = this_task
        self.server_queue = server_queue
        self.graceful_exit = graceful_exit
        self.grace_period = grace_period
        self._initiated = False

    async def supervise(self):
        await self.stack.enter_async_context(self.server_queue)
        helper_tasks = [
            tasks.spawn(func) for func in (
                self._on_graceful_exit,
                self._on_signal,
                self._join_server_tasks,
            )
        ]
        joiner = helper_tasks[-1]
        for task in helper_tasks:
            self.stack.push_async_callback(task.join)
        for task in helper_tasks:
            self.stack.callback(task.cancel)
        try:
            async for task in tasks.as_completed(helper_tasks):
                task.get_result_nonblocking()
                if task is joiner:
                    break
        except timers.Timeout:
            self._raise_error('grace period exceeded')

    async def _on_graceful_exit(self):
        await self.graceful_exit.wait()
        self._initiate_exit(None)

    async def _on_signal(self):
        signal_queue = signals.SignalQueue()
        try:
            for signum in EXIT_SIGNUMS:
                signal_queue.subscribe(signum)
            LOG.info('receive signal: %r', await signal_queue.get())
            self._initiate_exit(None)
            LOG.info('receive signal: %r', await signal_queue.get())
            self._raise_error('repeated signals')
        finally:
            signal_queue.close()

    async def _join_server_tasks(self):
        async for task in self.server_queue:
            exc = task.get_exception_nonblocking()
            if exc:
                self._raise_error('server task error: %r', task, exc_info=exc)
            else:
                self._initiate_exit('server task exit: %r', task)

    def _initiate_exit(self, reason, *log_args):
        if self._initiated:
            return
        message = 'initiate graceful exit'
        if reason:
            message = '%s due to %s' % (message, reason)
        LOG.info(message, *log_args)
        self.graceful_exit.set()
        self.server_queue.close()
        self.stack.enter_context(
            timers.timeout_after(self.grace_period, task=self.this_task)
        )
        self._initiated = True

    @staticmethod
    def _raise_error(reason, *log_args, exc_info=None):
        message = 'initiate non-graceful exit due to %s' % reason
        LOG.error(message, *log_args, exc_info=exc_info)
        raise SupervisorError(reason % log_args) from exc_info


async def supervise_handlers(
    handler_queue,
    helper_tasks,
):
    """Supervise handler tasks.

    * New handler tasks are spawned into ``handler_queue``.

    * It also supervises a (small) set of helper tasks.  These helper
      tasks perform certain functions for the server, and are considered
      essential to the server tasks (that is, if any one of them exits,
      this supervisor returns).

    * NOTE: Helper tasks also have to be put to ``handler_queue``.
    """
    async with handler_queue:
        async for task in handler_queue:
            exc = task.get_exception_nonblocking()
            if task in helper_tasks:
                if exc:
                    message = 'server helper task error: %r'
                    LOG.error(message, task, exc_info=exc)
                    raise SupervisorError(message % task) from exc
                else:
                    LOG.info('server helper task exit: %r', task)
                    break
            else:
                if exc:
                    LOG.error('handler task error: %r', task, exc_info=exc)
                else:
                    LOG.debug('handler task exit: %r', task)
