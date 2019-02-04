__all__ = [
    'TcpServer',
    'make_server_socket',
]

import errno
import logging
import socket

from g1.asyncs import kernels
from g1.asyncs import servers

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


class TcpServer:

    def __init__(
        self,
        server_socket,
        handle_client,
    ):
        self._server_socket = server_socket
        self._handle_client = handle_client

    async def serve(self):
        queue = kernels.TaskCompletionQueue()
        try:
            LOG.info('start server: %r', self._server_socket)
            await servers.supervise_handlers(
                queue,
                (queue.spawn(self._accept(queue)), ),
            )
            LOG.info('stop server: %r', self._server_socket)
        finally:
            await self._server_socket.close()

    async def _accept(self, queue):
        while True:
            try:
                sock, addr = await self._server_socket.accept()
            except OSError as exc:
                if exc.errno == errno.EBADF:
                    LOG.info('server socket close: %r', self._server_socket)
                    break
                else:
                    raise
            LOG.info('serve client: %r', addr)
            queue.spawn(self._handle_client(sock, addr))


def make_server_socket(
    address,
    *,
    family=socket.AF_INET,
    backlog=128,
    reuse_address=False,
    reuse_port=False,
    ssl_context=None,
):
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, reuse_address)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, reuse_port)
        sock.bind(address)
        sock.listen(backlog)
        if ssl_context:
            sock = ssl_context.wrap_socket(sock, server_side=True)
    except Exception:
        sock.close()
        raise
    return kernels.SocketAdapter(sock)
