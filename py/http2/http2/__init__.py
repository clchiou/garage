__all__ = [
    'HttpError',
    'Protocol',
    'Request',
    'Response',
]

import asyncio
import http
import logging
import socket
import traceback

from .http2 import Session
from .models import Request, Response


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


class HttpError(Exception):

    def __init__(self, status, *, reason=None, headers=None):
        super().__init__('%s: %s' % (status.name, reason))
        self.status = status
        self.reason = reason
        self.headers = headers


class Protocol(asyncio.Protocol):

    def __init__(self, handler_factory, loop=None):
        super().__init__()
        self.handler_factory = handler_factory
        self.handler = None
        self.loop = loop

    def connection_made(self, transport):
        if LOG.isEnabledFor(logging.DEBUG):
            LOG.debug('accept %r', transport.get_extra_info('peername'))

        self.transport = transport
        sock = self.transport.get_extra_info('socket')
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            LOG.exception('error when set TCP_NODELAY')

        self.handler = self.handler_factory()
        self.session = Session(self, transport)

    def data_received(self, data):
        LOG.debug('receive %d bytes', len(data))
        try:
            self.session.data_received(data)
        except:
            LOG.exception('error when receive data')
            self.transport.close()

    def connection_lost(self, exc):
        if LOG.isEnabledFor(logging.DEBUG):
            if exc:
                tb_lines = traceback.format_exception(
                    exc.__class__, exc, exc.__traceback__)
                LOG.debug('close connection\n%s', ''.join(tb_lines))
            else:
                LOG.debug('close connection')
        if self.handler is not None:
            self.session.close()
            self.handler = None

    # Called from http2.Session

    def handle_request(self, stream_id, request):
        for name, value in request.headers.items():
            if name.lower() == b'expect' and b'100-continue' in value.lower():
                LOG.debug('reject "expect: 100-continue"')
                response = Response()
                response.headers[b':status'] = (
                    b'%d' % http.HTTPStatus.EXPECTATION_FAILED.value)
                self.session.handle_response(stream_id, response)
                return
        LOG.debug('handle request of stream %d', stream_id)
        asyncio.ensure_future(self._handle(stream_id, request), loop=self.loop)

    async def _handle(self, stream_id, request):
        response = Response()
        try:
            await self.handler(request, response)
        except HttpError as e:
            LOG.debug('HTTP status: %s', e)
            await self._submit_status(stream_id, e.status, e.reason, e.headers)
        except:
            LOG.exception(
                'error when handling request on stream %d', stream_id)
            await self._submit_status(
                stream_id, http.HTTPStatus.INTERNAL_SERVER_ERROR, None, None)
            self.session.close_stream(stream_id)
        else:
            for req, rep in response._push_promises:
                promised_stream_id = self.session.submit_push_promise(
                        stream_id, req)
                LOG.debug('push promise on stream %d', promised_stream_id)
                if rep:
                    self.session.handle_response(promised_stream_id, rep)
                else:
                    self.handle_request(promised_stream_id, req)
            self.session.handle_response(stream_id, response)

    async def _submit_status(self, stream_id, status, reason, headers):
        response = Response()
        response.headers[b':status'] = b'%d' % status.value
        if headers:
            response.headers.update(headers)
        if reason:
            await response.write(reason.encode('utf-8'))
            response.close()
        self.session.handle_response(stream_id, response)
