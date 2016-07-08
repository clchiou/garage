"""Asynchronous HTTP/2 service container."""

__all__ = [
    'ServerConfig',
    'ServerConfigError',
    'server',
]

import asyncio
import logging
from functools import partial

import http2
import http2.utils
from garage import asserts
from garage.asyncs.futures import one_completed
from garage.asyncs.processes import ProcessOwner, process
from garage.asyncs.utils import CircuitBreaker, tcp_server


LOG = logging.getLogger(__name__)


class ServerConfigError(Exception):
    pass


class ServerConfig:

    CONFIG_NAMES = frozenset((
        # Basic configurations
        'name',
        'host', 'port',
        'backlog',
        # SSL
        'certificate', 'private_key',
        # HTTP request handler
        'make_handler',
        # Error handling
        'circuit_breaker',
    ))

    BACKLOG = 256

    def __init__(self):
        for name in self.CONFIG_NAMES:
            setattr(self, name, None)
        self.name = 'http.server'
        self.backlog = self.BACKLOG
        self.circuit_breaker = CircuitBreaker(count=1, period=None)

    def __setattr__(self, name, value):
        if name not in self.CONFIG_NAMES:
            raise AttributeError('Unknown config name: %s' % name)
        super().__setattr__(name, value)

    def make_server(self):
        return server(self)

    def validate(self):
        if self.port is None:
            raise ServerConfigError('port is required')
        if (self.certificate is None) != (self.private_key is None):
            raise ServerConfigError('Require both certificate and private key')
        if self.make_handler is None:
            raise ServerConfigError('make_handler is required')

    def make_ssl_context(self):
        self.validate()
        if self.certificate and self.private_key:
            return http2.utils.make_ssl_context(
                self.certificate,
                self.private_key,
            )
        else:
            return None


@process
async def server(exit, config, *, loop=None):
    """Make a server process."""
    config.validate()

    make_handler = config.make_handler
    create_server = partial(
        (loop or asyncio.get_event_loop()).create_server,
        lambda: http2.Protocol(make_handler),
        host=config.host, port=config.port,
        backlog=config.backlog,
        ssl=config.make_ssl_context(),
    )

    async with ProcessOwner() as server_owner:
        while True:
            server_owner.own(tcp_server(create_server))
            proc = await one_completed([], [server_owner.proc, exit])
            try:
                await proc
            except Exception:
                LOG.exception('%s: http server crash', config.name)
            if not config.circuit_breaker.count(raises=False):
                LOG.warning('%s: circuit breaker disconnect', config.name)
                return
            asserts.postcond(proc is server_owner.proc)
            await server_owner.disown()
