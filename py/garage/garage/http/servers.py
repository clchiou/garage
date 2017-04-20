"""HTTP server."""

__all__ = [
    'ClientError',
    'Server',
]

import logging

import curio

import http2

from garage import asserts
from garage import asyncs


LOG = logging.getLogger(__name__)


class ClientError(Exception):
    """Represent HTTP 4xx status code."""

    def __init__(self, status, *,
                 headers=None,
                 message='',
                 internal_message=''):
        asserts.precond(400 <= status < 500)
        super().__init__(internal_message or message)
        self.status = status
        self.headers = headers
        self.message = message.encode('utf8')

    def as_response(self):
        return http2.Response(
            status=self.status, headers=self.headers, body=self.message)


class Server:
    """Serve one client connection."""

    def __init__(self, handler, *, timeout=None):
        self.handler = handler
        self.timeout = timeout

    async def __call__(self, client_socket, client_address):
        session = http2.Session(client_socket)
        async with \
                asyncs.TaskSet() as tasks, \
                await asyncs.cancelling.spawn(self._join(tasks)) as joiner, \
                await asyncs.cancelling.spawn(session.serve()) as server:
            async for stream in session:
                await tasks.spawn(self._run_handler(stream))
            await server.join()
            tasks.graceful_exit()
            await joiner.join()

    @staticmethod
    async def _join(runners):
        async for runner in runners:
            try:
                await runner.join()
            except Exception:
                # This should not be possible as _run_handler never let
                # exception leave it!
                LOG.exception('error pops out from handler runner: %r', runner)

    async def _run_handler(self, stream):
        try:
            async with curio.timeout_after(self.timeout):
                await self.handler(stream)
        except ClientError as exc:
            LOG.warning('request handler rejects request because %s: %r',
                        exc, self.handler, exc_info=True)
            # If a response has been submitted, at this point all we can
            # do is rst_stream
            if stream.response:
                await stream.submit_rst_stream()
            else:
                await stream.submit_response(exc.as_response())
        except Exception:
            LOG.exception('request handler errs: %r', self.handler)
            # If a response has been submitted, at this point all we can
            # do is rst_stream
            if stream.response:
                await stream.submit_rst_stream()
            else:
                await stream.submit_response(
                    http2.Response(status=http2.Status.INTERNAL_SERVER_ERROR))
