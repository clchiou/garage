__all__ = [
    'make_server_socket',
    'serve',
    'synchronous',
]

from functools import wraps

from curio import socket
import curio

from garage import asyncs
from garage.assertions import ASSERT


def make_server_socket(
        address, *,
        family=socket.AF_INET,
        backlog=128,
        reuse_address=True,
        reuse_port=False):
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        if reuse_address:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        if reuse_port:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
        sock.bind(address)
        sock.listen(backlog)
    except Exception:
        # XXX: I would prefer a non-async make_server_socket and that
        # forbids me calling sock.close() here bucause it's async; so I
        # have to call the underlying socket object's close() directly.
        # Since no one else is referencing to this sock object, this
        # hack should be fine.
        sock._socket.close()
        raise
    else:
        return sock


async def serve(graceful_exit, make_server_socket, handle_client, *,
                make_ssl_context=None,
                logger=None):

    if logger is None:
        import logging
        logger = logging.getLogger(__name__)

    connections = {}

    async def accept_clients(handlers):
        async with make_server_socket() as server_socket:
            if make_ssl_context:
                server_socket = make_ssl_context().wrap_socket(
                    server_socket, server_side=True)
            while True:
                sock, addr = await server_socket.accept()
                logger.debug('serve client from: %r', addr)
                handler = await handlers.spawn(handle_client(sock, addr))
                connections[handler] = sock

    async def join_client_handlers(handlers):
        async for handler in handlers:
            connections.pop(handler, None)
            if handler.exception:
                logger.error(
                    'err in client handler: %r',
                    handler, exc_info=handler.exception,
                )

    async with asyncs.TaskSet() as handlers, asyncs.TaskStack() as stack:

        joiner = await stack.spawn(join_client_handlers(handlers))

        acceptor = await stack.spawn(accept_clients(handlers))

        await stack.spawn(graceful_exit.wait())

        task = await stack.wait_any()
        if task in (joiner, acceptor):
            logger.error('server task is terminated: %r', task)
            return await task.join()

        ASSERT.true(graceful_exit.is_set())
        logger.info('initiate graceful exit')
        await acceptor.cancel()
        handlers.graceful_exit()
        # If it's not a graceful exit, the tasks will be cancelled; so
        # we don't need to close sockets on that case, right?
        for conn in connections.values():
            await asyncs.close_socket_and_wakeup_task(conn)
        await joiner.join()


def synchronous(coro_func):
    """Transform the decorated coroutine function into a synchronous
       function.
    """
    @wraps(coro_func)
    def wrapper(*args, **kwargs):
        return curio.run(coro_func(*args, **kwargs))
    return wrapper
