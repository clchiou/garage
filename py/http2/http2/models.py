__all__ = [
    'Request',
    'Response',
]

import io
from collections import OrderedDict


class Request:

    def __init__(self):
        self.headers = OrderedDict()
        self.body = None
        self._body_buffer = io.BytesIO()

    def write(self, data):
        self._body_buffer.write(data)

    def close(self):
        self.body = self._body_buffer.getvalue()
        self._body_buffer.close()


class Response:

    def __init__(self):
        self.headers = OrderedDict()
        self.body = None
