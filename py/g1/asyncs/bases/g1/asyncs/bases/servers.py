"""Servers.

For now here are just helper functions for writing servers.

While not always the case, a server usually looks like this:

    class Server:

        def __init__(self, handler):
            self._handler = handler

        async def serve(self):
            pass  # Serve requests.

        def shutdown(self):
            pass  # Request server to shut down gracefully.
"""

__all__ = [
    'ServerError',
    'supervise_server',
]

import logging

from . import tasks

LOG = logging.getLogger(__name__)


class ServerError(Exception):
    """Raise when a server task errs out."""


async def supervise_server(queue, server_tasks):
    """Supervise server and handler tasks.

    * Server tasks are responsible for non-handler functionalities, such
      as accepting incoming connections.

    * Handler tasks are responsible for processing one client request.

    * Both server and handler tasks are spawned into the queue.

    * Server tasks are assumed to be essential to the server.  When any
      one of them exits or errs out, the supervisor exits, too.
    """
    async with queue:
        async for task in queue:
            exc = task.get_exception_nonblocking()
            if task in server_tasks:
                if exc:
                    if isinstance(exc, tasks.Cancelled):
                        # Log at DEBUG rather than INFO level for the
                        # same reason below.
                        LOG.debug('server task is cancelled: %r', task)
                    else:
                        raise ServerError(
                            'server task error: %r' % task
                        ) from exc
                else:
                    # Log at DEBUG rather than INFO level because
                    # supervise_server could actually be called in a
                    # request handler (when the handler is sufficiently
                    # complex), and we do not want to over-log at INFO
                    # level.
                    LOG.debug('server task exit: %r', task)
                    break
            else:
                if exc:
                    if isinstance(exc, tasks.Cancelled):
                        LOG.debug('handler task is cancelled: %r', task)
                    else:
                        LOG.error('handler task error: %r', task, exc_info=exc)
                else:
                    LOG.debug('handler task exit: %r', task)
