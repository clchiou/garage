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

import logging
import signal

from g1.asyncs import kernels

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

    * ``server_queue`` is a ``TaskCompletionQueue`` of the server tasks.
      It is closed when this supervisor begins stopping server tasks.

    * ``graceful_exit`` is an event object that, once set, this
      supervisor will begin stopping servers gracefully.  Any task may
      wait on this event object to get notified on graceful exit.
    """

    async with server_queue:

        exit_waiter = server_queue.spawn(
            graceful_exit.wait,
            wait_for_completion=False,
        )

        signal_handler = server_queue.spawn(
            handle_signal(graceful_exit),
            wait_for_completion=False,
        )

        cancel_timeout = None

        def initiate_graceful_exit(reason, *log_args):
            nonlocal cancel_timeout
            if cancel_timeout:
                return
            message = 'initiate graceful exit'
            if reason:
                message = '%s due to %s' % (message, reason)
            LOG.info(message, *log_args)
            graceful_exit.set()
            cancel_timeout = kernels.timeout_after(grace_period)

        def initiate_non_graceful_exit(reason, *log_args, exc_info=None):
            message = 'initiate non-graceful exit due to %s' % reason
            LOG.error(message, *log_args, exc_info=exc_info)
            raise SupervisorError(reason % log_args) from exc_info

        try:
            async for task in server_queue.as_completed():
                server_queue.close()
                exc = task.get_exception_nonblocking()
                if task is exit_waiter:
                    initiate_graceful_exit(None)
                elif task is signal_handler:
                    initiate_non_graceful_exit('repeated signals')
                elif exc:
                    initiate_non_graceful_exit(
                        'server task error: %r', task, exc_info=exc
                    )
                else:
                    initiate_graceful_exit('server task exit: %r', task)

        except kernels.Timeout:
            initiate_non_graceful_exit('grace period exceeded')

        finally:
            exit_waiter.cancel()
            signal_handler.cancel()
            if cancel_timeout:
                cancel_timeout()


async def handle_signal(graceful_exit):
    signal_queue = kernels.SignalQueue()
    try:
        for signum in EXIT_SIGNUMS:
            signal_queue.subscribe(signum)
        # Upon the first signal, initiate the graceful exit, and upon
        # the second one, initiate the non-graceful exit (via returning
        # from this coroutine).
        for _ in range(2):
            LOG.info('receive signal: %r', await signal_queue.get())
            graceful_exit.set()
    finally:
        signal_queue.close()


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
        async for task in handler_queue.as_completed():
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
