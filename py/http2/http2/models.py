__all__ = [
    'Request',
    'Response',
]

from collections import OrderedDict


class Request:

    def __init__(self):
        self.headers = OrderedDict()


class Response:

    def __init__(self):
        self.headers = OrderedDict()
        self.body = None
