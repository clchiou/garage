__all__ = [
    'MessagingError',
    'ServiceState',
    'ServiceMixin',
    'remote_call',
    'serve_one',
    'serve_forever',
]

import asyncio
import enum
import json  # TODO: Make serialization format pluggable.
import logging

from garage import asserts

import nanomsg as nn


LOG = logging.getLogger(__name__)


GRACEFUL_PERIOD = 30  # Unit: seconds


class MessagingError(Exception):
    pass


class ServiceState(enum.Enum):

    INITIALIZING = 'INITIALIZING'
    INITIALIZED = 'INITIALIZED'

    STARTING = 'STARTING'
    STARTED = 'STARTED'

    STOPPING = 'STOPPING'
    STOPPED = 'STOPPED'


class ServiceMixin:
    """Non-restartable service mixin."""

    def __init__(self, serve,
                 name='?',
                 on_starting=None,
                 on_stopping=None,
                 graceful_period=GRACEFUL_PERIOD,
                 *, loop=None):
        self.__name = name
        self.__state = ServiceState.INITIALIZING
        self.__server = None
        self.__serve = serve
        self.__on_starting = on_starting
        self.__on_stopping = on_stopping
        self.__graceful_period = graceful_period
        self.__loop = loop
        self.__state = ServiceState.INITIALIZED

    def __repr__(self):
        return '<%s %s>' % (self.__name, self.__state.value)

    async def start(self):
        asserts.precond(self.__state is ServiceState.INITIALIZED)
        self.__state = ServiceState.STARTING
        LOG.info('%r: start', self)
        if self.__on_starting:
            await self.__on_starting()
        self.__server = asyncio.ensure_future(self.__serve(), loop=self.__loop)
        self.__state = ServiceState.STARTED

    async def stop(self):
        asserts.precond(self.__state is ServiceState.STARTED)
        self.__state = ServiceState.STOPPING
        LOG.info('%r: stop', self)
        if self.__on_stopping:
            await self.__on_stopping()
        done, pending = await asyncio.wait(
            [self.__server],
            loop=self.__loop,
            timeout=self.__graceful_period,
        )
        for fut in done:
            try:
                fut.result()
            except Exception:
                LOG.exception('%r: err when stopping service', self)
        if pending:
            LOG.warning('%r: leave %d pending tasks and exit',
                        self, len(pending))
        self.__server = None
        self.__state = ServiceState.STOPPED


async def remote_call(sock, method, request):
    message = {'method': method, 'request': request}
    await sock.send(json.dumps(message).encode('ascii'))
    with await sock.recv() as response:
        return json.loads(bytes(response.as_memoryview()).decode('ascii'))


async def serve_forever(sock, methods, name=None):
    while True:
        try:
            await serve_one(sock, methods)
        except nn.Closed:
            break
        except MessagingError:
            LOG.warning('%r: invalid message', name, exc_info=True)
        except Exception:
            LOG.exception('%r: err when processing message', name)
    LOG.info('%r: exit messaging loop', name)


async def serve_one(sock, methods):
    with await sock.recv() as msg:
        message = json.loads(bytes(msg.as_memoryview()).decode('ascii'))

    method_name = message.get('method')
    request = message.get('request')
    if not (method_name and request):
        raise MessagingError('invalid message %r', message)

    method = methods.get(method_name)
    if not method:
        raise MessagingError('method not found %r', method_name)

    response = await method(request)

    await sock.send(json.dumps(response).encode('ascii'))
