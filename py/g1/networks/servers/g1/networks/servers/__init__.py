__all__ = [
    'SocketServer',
]

import errno
import logging

from g1.asyncs.bases import servers
from g1.asyncs.bases import tasks

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


class SocketServer:

    def __init__(self, socket, handler, num_connections=0):
        self._socket = socket
        self._handler = handler
        self._num_connections = num_connections

    async def serve(self):
        LOG.info('start server: %r', self._socket)
        with self._socket:
            if self._num_connections <= 0:
                capacity = self._num_connections
            else:
                # +1 for the `_accept` task.
                capacity = self._num_connections + 1
            async with tasks.CompletionQueue(capacity) as queue:
                await servers.supervise_server(
                    queue,
                    (queue.spawn(self._accept(queue)), ),
                )
        LOG.info('stop server: %r', self._socket)

    async def _accept(self, queue):
        while True:
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
