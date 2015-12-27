__all__ = [
    'Http2Protocol',
]

import asyncio
import logging
import traceback
from collections import namedtuple

from .http2 import Session
from .models import Response


LOG = logging.getLogger(__name__)


class Http2Protocol(asyncio.Protocol):

    def __init__(self, handler_factory, loop=None):
        super().__init__()
        self.handler_factory = handler_factory
        self.handler = None
        self.loop = loop
        self._request_metadata = {}

    def connection_made(self, transport):
        if LOG.isEnabledFor(logging.DEBUG):
            peername = transport.get_extra_info('peername')
            LOG.debug('accept %s:%d', peername[0], peername[1])
        self.handler = self.handler_factory()
        self.session = Session(self, transport)

    def data_received(self, data):
        self.session.data_received(data)

    def connection_lost(self, exc):
        if LOG.isEnabledFor(logging.DEBUG):
            if exc:
                tb_lines = traceback.format_exception(
                    exc.__class__, exc, exc.__traceback__)
                LOG.debug('close connection\n%s', ''.join(tb_lines))
            else:
                LOG.debug('close connection')
        self.session.close()
        self.handler = None

    # Called from http2.Session

    def handle_request(self, stream_id, request, expect_100_continue=False):
        if request in self._request_metadata:
            return
        LOG.debug('handle request of stream %d', stream_id)
        self._request_metadata[request] = RequestMetadata(
            stream_id=stream_id,
            expect_100_continue=expect_100_continue,
        )
        asyncio.ensure_future(self._handle(stream_id, request), loop=self.loop)

    async def _handle(self, stream_id, request):
        response = Response()
        await self.handler(request, response)
        self.session.handle_response(stream_id, response)
        self._request_metadata.pop(request)

    # Called from models.Request

    def on_read_body(self, request):
        metadata = self._request_metadata[request]
        if metadata.expect_100_continue:
            self.session.submit_non_final_response(metadata.stream_id, 100)


RequestMetadata = namedtuple(
    'RequestMetadata',
    'stream_id expect_100_continue',
)
