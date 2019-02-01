__all__ = [
    'TcpServer',
    'TcpServerError',
    'make_server_socket',
]

import errno
import logging
import socket

from g1.asyncs import kernels

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


class TcpServerError(Exception):
    pass


class TcpServer:

    def __init__(
        self,
        server_socket,
        handle_client,
    ):
        self._server_socket = server_socket
        self._handle_client = handle_client

    async def serve(self):
        async with kernels.TaskCompletionQueue() as queue:

            server_tasks = frozenset((kernels.spawn(self._accept(queue)), ))
            for task in server_tasks:
                queue.put(task)

            try:
                LOG.info('start server: %r', self._server_socket)

                async for task in queue.as_completed():
                    exc = await task.get_exception()
                    if task in server_tasks:
                        if exc:
                            message = 'server task error: %r' % task
                            raise TcpServerError(message) from exc
                        else:
                            LOG.info('server task exit: %r', task)
                            break
                    elif exc:
                        LOG.error('handler error: %r', task, exc_info=exc)

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
            queue.put(kernels.spawn(self._handle_client(sock, addr)))


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
