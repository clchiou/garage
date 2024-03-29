__all__ = [
    'SocketServer',
]

import errno
import logging

from g1.asyncs.bases import servers
from g1.asyncs.bases import tasks
from g1.bases import times
from g1.bases.loggings import ONCE_PER

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


class SocketServer:

    def __init__(self, socket, handler, max_connections=0):
        self._socket = socket
        self._handler = handler
        self._max_connections = max_connections

    async def serve(self):
        LOG.debug('start server: %r', self._socket)
        with self._socket:
            if self._max_connections <= 0:
                capacity = self._max_connections
            else:
                # +1 for the `_accept` task.
                capacity = self._max_connections + 1
            async with tasks.CompletionQueue(capacity) as queue:
                await servers.supervise_server(
                    queue,
                    (queue.spawn(self._accept(queue)), ),
                )
        LOG.debug('stop server: %r', self._socket)

    async def _accept(self, queue):
        while True:
            if queue.is_full():
                if ONCE_PER.check(600, times.Units.SECONDS):
                    LOG.error(
                        'handler task queue is full; '
                        'we cannot accept any new connections'
                    )
            await queue.puttable()
            try:
                sock, addr = await self._socket.accept()
            except OSError as exc:
                if exc.errno == errno.EBADF:
                    LOG.info('server socket close: %r', self._socket)
                    break
                raise
            LOG.debug('serve client: %r', addr)
            queue.spawn(self._handler(sock, addr))

    def shutdown(self):
        self._socket.close()
