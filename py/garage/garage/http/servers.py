"""HTTP server."""

__all__ = [
    'ClientError',
    'Redirection',
    'ServerError',
    'Server',
]

import logging

import curio

import http2

from garage import asyncs
from garage.assertions import ASSERT


LOG = logging.getLogger(__name__)


class HttpError(Exception):

    @staticmethod
    def assert_status(status):
        pass

    def __init__(
            self, status, *,
            headers=None,
            message='', internal_message=''):
        self.assert_status(status)
        super().__init__(internal_message or message)
        self.status = status
        self.headers = headers
        if isinstance(message, str):
            message = message.encode('utf8')
        self.message = message

    def as_response(self):
        return http2.Response(
            status=self.status,
            headers=self.headers,
            body=self.message,
        )


class Redirection(Exception):
    """Represent HTTP 3xx status code."""

    def __init__(self, status, location):
        ASSERT(300 <= status < 400, 'expect 3xx status: %s', status)
        if isinstance(location, str):
            location = location.encode('ascii')
        self.status = status
        self.location = location

    def as_response(self):
        return http2.Response(
            status=self.status,
            headers=[(b'Location', self.location)],
        )


class ClientError(HttpError):
    """Represent HTTP 4xx status code."""

    @staticmethod
    def assert_status(status):
        ASSERT(400 <= status < 500, 'expect 4xx status: %s', status)


class ServerError(HttpError):
    """Represent HTTP 5xx status code."""

    @staticmethod
    def assert_status(status):
        ASSERT(500 <= status < 600, 'expect 5xx status: %s', status)


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
            if runner.exception:
                # This should not be possible as _run_handler never let
                # exception leave it!
                LOG.error(
                    'error pops out from handler runner: %r',
                    runner, exc_info=runner.exception,
                )

    async def _run_handler(self, stream):
        LOG.info(
            '%s: %s %s',
            stream, stream.request.method.name, stream.request.path,
        )
        try:
            try:
                async with curio.timeout_after(self.timeout):
                    await self.handler(stream)
            except Redirection as redirection:
                await stream.submit_response(redirection.as_response())
        except http2.StreamClosed:
            LOG.warning(
                'stream is closed: %s: %s %s',
                stream, stream.request.method.name, stream.request.path,
            )
        except HttpError as exc:
            response = exc.as_response()
            if isinstance(exc, ClientError):
                LOG.warning(
                    'request handler rejects request because %s: %s: %s %s %s',
                    exc,
                    stream, stream.request.method.name, stream.request.path,
                    response.status,
                    exc_info=True,
                )
            else:
                # Whether an HTTP 5xx status code is an error should be
                # decided at application layer; we just log a warning.
                LOG.warning(
                    'request handler throws: %s: %s %s %s',
                    stream, stream.request.method.name, stream.request.path,
                    response.status,
                    exc_info=True,
                )
            await self._submit_error(stream, response)
        except Exception:
            LOG.exception(
                'request handler errs: %s: %s %s',
                stream, stream.request.method.name, stream.request.path,
            )
            await self._submit_error(
                stream,
                http2.Response(status=http2.Status.INTERNAL_SERVER_ERROR),
            )

    async def _submit_error(self, stream, response):
        try:
            if stream.response:
                # If a response has been submitted, at this point all we can
                # do is rst_stream.
                await stream.submit_rst_stream()
            else:
                await stream.submit_response(response)
        except http2.StreamClosed:
            LOG.warning(
                'stream is closed before error could be sent: %s: %s %s %s',
                stream, stream.request.method.name, stream.request.path,
                response.status,
            )
