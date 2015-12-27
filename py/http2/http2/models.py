__all__ = [
    'Request',
    'Response',
]

import asyncio
import io
from collections import OrderedDict


class Request:

    def __init__(self, protocol):
        self.headers = OrderedDict()
        self._protocol = protocol
        self._body = None
        self._body_future = asyncio.Future(loop=protocol.loop)
        self._body_buffer = io.BytesIO()

    # Called from application handler.

    @property
    async def body(self):
        if self._body is None:
            self._protocol.on_read_body(self)
            self._body = await self._body_future
        return self._body

    # Called from http2.Session

    def write(self, data):
        self._body_buffer.write(data)

    def close(self):
        self._body_future.set_result(self._body_buffer.getvalue())
        self._body_buffer.close()


class Response:

    def __init__(self):
        self.headers = OrderedDict()
        self.body = None
        self._body_buffer = io.BytesIO()

    # Called from application handler.

    def write(self, data):
        self._body_buffer.write(data)

    def close(self):
        self.body = self._body_buffer.getvalue()
        self._body_buffer.close()
