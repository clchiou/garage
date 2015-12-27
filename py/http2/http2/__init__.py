__all__ = [
    'Http2Protocol',
]

import asyncio
import logging

from .http2 import Session
from .models import Response


LOG = logging.getLogger(__name__)


class Http2Protocol(asyncio.Protocol):

    def __init__(self, handler_factory, loop=None):
        super().__init__()
        self.handler_factory = handler_factory
        self.handler = None
        self.loop = loop

    def connection_made(self, transport):
        if LOG.isEnabledFor(logging.DEBUG):
            peername = transport.get_extra_info('peername')
            LOG.debug('accept %s:%d', peername[0], peername[1])
        self.handler = self.handler_factory()
        self.session = Session(self, transport)

    def data_received(self, data):
        self.session.data_received(data)

    def connection_lost(self, exc):
        LOG.debug('close connection', exc_info=bool(exc))
        self.session.close()
        self.handler = None

    # Called from http2.Session

    def handle_request(self, stream_id, request):
        LOG.debug('handle request of stream %d', stream_id)
        asyncio.ensure_future(self._handle(stream_id, request), loop=self.loop)

    async def _handle(self, stream_id, request):
        response = Response()
        await self.handler(request, response)
        self.session.handle_response(stream_id, response)
