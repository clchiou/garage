"""Asynchronous HTTP/2 server container."""

__all__ = [
    'ServerConfig',
    'ServerConfigError',
]

import asyncio
from functools import partial

import http2
import http2.utils
from garage.asyncs.servers import tcp_server


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
    ))

    BACKLOG = 256

    def __init__(self):
        for name in self.CONFIG_NAMES:
            setattr(self, name, None)
        self.backlog = self.BACKLOG

    def __setattr__(self, name, value):
        if name not in self.CONFIG_NAMES:
            raise AttributeError('Unknown config name: %s' % name)
        super().__setattr__(name, value)

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

    def make_server(self, *, loop=None):
        self.validate()
        return tcp_server(name=self.name, create_server=partial(
            (loop or asyncio.get_event_loop()).create_server,
            partial(http2.Protocol, self.make_handler),
            host=self.host, port=self.port,
            backlog=self.backlog,
            ssl=self.make_ssl_context(),
        ))
