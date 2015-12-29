__all__ = [
    'Request',
    'Response',
]

import asyncio
import io
from collections import OrderedDict


class Request:

    def __init__(self, protocol, *, _copy=None):
        if _copy:
            self.headers = _copy.headers.copy()
            self._body_future = _copy._body_future
            self._body_buffer = None  # You cannot write to a copy.
        else:
            self.headers = OrderedDict()
            self._body_future = asyncio.Future(loop=protocol.loop)
            self._body_buffer = io.BytesIO()
        self._body = None

    # Called from application handler.

    @property
    async def body(self):
        if self._body is None:
            self._body = await self._body_future
        return self._body

    def copy(self):
        return Request(None, _copy=self)

    # Called from http2.Session

    def write(self, data):
        assert self._body_buffer is not None, 'you cannot write to a copy'
        self._body_buffer.write(data)

    def close(self):
        assert self._body_buffer is not None, 'you cannot close a copy'
        self._body_future.set_result(self._body_buffer.getvalue())
        self._body_buffer.close()


class Response:

    def __init__(self):
        self.headers = OrderedDict()
        self.body = None
        self._body_buffer = io.BytesIO()
        self._push_promises = []

    # Called from application handler.

    def push(self, request, response=None):
        self._push_promises.append((request, response))

    async def write(self, data):
        self._body_buffer.write(data)

    async def close(self):
        self.body = self._body_buffer.getvalue()
        self._body_buffer.close()
