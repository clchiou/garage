__all__ = [
    'make_server_socket',
    'serve',
]

from curio import socket

from garage import asserts
from garage import asyncs


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

    async def accept_clients(handlers):
        async with make_server_socket() as server_socket:
            if make_ssl_context:
                server_socket = make_ssl_context().wrap_socket(
                    server_socket, server_side=True)
            while True:
                sock, addr = await server_socket.accept()
                logger.info('serve client from: %r', addr)
                await handlers.spawn(handle_client(sock, addr))

    async def join_client_handlers(handlers):
        async for handler in handlers:
            try:
                await handler.join()
            except Exception:
                logger.exception('err in client handler: %r', handler)

    async with \
            asyncs.TaskSet() as handlers, \
            await asyncs.cancelling.spawn(
                join_client_handlers(handlers)) as joiner, \
            await asyncs.cancelling.spawn(
                accept_clients(handlers)) as acceptor:

        task = await asyncs.select([graceful_exit.wait(), joiner, acceptor])
        if task in (joiner, acceptor):
            logger.error('server task is terminated: %r', task)
            return await task.join()

        asserts.postcond(graceful_exit.is_set())
        logger.info('initiate graceful exit')
        await acceptor.cancel()
        handlers.graceful_exit()
        await joiner.join()
