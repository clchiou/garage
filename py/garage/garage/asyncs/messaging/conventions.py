__all__ = [
    'ClientBase',
    'InterfaceSpec',
    'validate_request',

    'BACKLOG',
    'HttpServiceBase',
]

import asyncio
import logging
from collections import namedtuple
from functools import partialmethod

from garage import asserts

from . import GRACEFUL_PERIOD, ServiceMixin
from . import remote_call as _remote_call


LOG = logging.getLogger(__name__)


InterfaceSpec = namedtuple('InterfaceSpec', '''
    method request_types response_type errno_type
''')


class ClientMeta(type):

    def __new__(mcs, name, bases, namespace, interface_specs=None):
        if interface_specs:
            for spec in interface_specs:
                asserts.precond(spec.method not in namespace)
                namespace[spec.method] = partialmethod(
                    ClientBase.remote_call,
                    spec.method,
                    spec.request_types,
                    spec.response_type,
                    spec.errno_type,
                )
        return super().__new__(mcs, name, bases, namespace)

    def __init__(cls, name, bases, namespace, **_):
        super().__init__(name, bases, namespace)


class ClientBase(metaclass=ClientMeta):

    def __init__(self, sock):
        self.__sock = sock

    async def remote_call(
            self, method, request_types, response_type, errno_type,
            **request):
        asserts.precond(
            validate_request(request_types, request), '%r', request)
        response, errno = await _remote_call(self.__sock, method, request)
        if response is not None:
            response = response_type(response)
        if errno is not None:
            errno = errno_type(errno)
        return response, errno


def validate_request(request_types, request):
    return (
        isinstance(request, dict) and
        len(request_types) == len(request) and
        all(key in request_types and isinstance(value, request_types[key])
            for key, value in request.items())
    )


BACKLOG = 512


class HttpServiceBase(ServiceMixin):

    def __init__(self, serve, host, port,
                 name='?',
                 backlog=BACKLOG, ssl_context=None,
                 graceful_period=GRACEFUL_PERIOD,
                 *, loop=None):
        # Restrict dependency to http2 locally.
        from http2 import Protocol

        super().__init__(
            self.__serve,
            name=name,
            on_starting=self.__on_starting,
            on_stopping=self.__on_stopping,
            graceful_period=graceful_period,
            loop=loop,
        )

        self.__create_server = lambda l: l.create_server(
            lambda: Protocol(lambda: serve, loop=l),
            host=host, port=port,
            backlog=backlog,
            ssl=ssl_context,
        )
        self.__server = None
        self.__server_exit = asyncio.Event(loop=loop)
        self.__loop = loop

    async def __on_starting(self):
        self.__server = await self.__create_server(
            self.__loop or asyncio.get_event_loop())
        del self.__create_server
        if LOG.isEnabledFor(logging.INFO):
            for sock in self.__server.sockets:
                LOG.info('%r: listen on %r', self, sock.getsockname())
        LOG.info('%r: serving...', self)

    async def __serve(self):
        await self.__server_exit.wait()
        LOG.info('%r: shutdown http server', self)
        self.__server.close()
        await self.__server.wait_closed()

    async def __on_stopping(self):
        self.__server_exit.set()
