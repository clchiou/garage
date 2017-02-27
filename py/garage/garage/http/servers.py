"""HTTP server."""

__all__ = [
    'Server',
]

import logging

import curio

import http2

from garage import asyncs


LOG = logging.getLogger(__name__)


class Server:
    """Serve one client connection."""

    @classmethod
    def make(cls, *, handler=None, router=None, **kwargs):
        assert (handler is None) != (router is None)
        if router:
            from . import routers
            handler = routers.RouterHandler(router)
        from . import handlers
        return cls(handlers.HandlerContainer(handler), **kwargs)

    def __init__(self, handler, *, timeout=None):
        self.handler = handler
        self.timeout = timeout

    async def __call__(self, client_socket, client_address):
        session = http2.Session(client_socket)
        async with \
                asyncs.TaskSet() as tasks, \
                await asyncs.cancelling.spawn(self.__join(tasks)) as joiner, \
                await asyncs.cancelling.spawn(session.serve()) as server:
            async for stream in session:
                await tasks.spawn(self.__run_handler(stream))
            await server.join()
            tasks.graceful_exit()
            await joiner.join()

    @staticmethod
    async def __join(runners):
        async for runner in runners:
            try:
                await runner.join()
            except Exception:
                # This should not be possible as __run_handler never let
                # exception leave it!
                LOG.exception('error pops out from handler runner: %r', runner)

    async def __run_handler(self, stream):
        try:
            async with curio.timeout_after(self.timeout):
                await self.handler(stream)
        except Exception:
            LOG.exception('request handler errs: %r', self.handler)
            await stream.submit_rst_stream()
