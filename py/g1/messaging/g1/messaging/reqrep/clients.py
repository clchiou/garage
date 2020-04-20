__all__ = [
    'Client',
]

import nng
import nng.asyncs

from g1.bases import classes
from g1.bases import collections
from g1.bases.assertions import ASSERT

from . import utils


class Client:

    def __init__(self, request_type, response_type, wiredata):
        self.socket = nng.asyncs.Socket(nng.Protocols.REQ0)
        self.transceive = Transceiver(self.socket, response_type, wiredata)
        self.m = collections.Namespace(
            **{
                name: Method(name, request_type, self.transceive)
                for name in request_type.m
            }
        )

    __repr__ = classes.make_repr('{self.socket!r}')

    def __enter__(self):
        self.socket.__enter__()
        return self

    def __exit__(self, *args):
        return self.socket.__exit__(*args)


class Transceiver:

    def __init__(self, socket, response_type, wiredata):
        self._socket = socket
        self._response_type = response_type
        self._wiredata = wiredata

    async def __call__(self, request):
        with nng.asyncs.Context(ASSERT.not_none(self._socket)) as context:
            await context.send(self._wiredata.to_lower(request))
            wire_response = await context.recv()
            return self._wiredata.to_upper(self._response_type, wire_response)


class Method:

    def __init__(self, name, request_type, transceive):
        self._name = name
        self._request_type = request_type
        self._transceive = transceive

    async def __call__(self, **kwargs):
        response = await self._transceive(
            self._request_type(
                args=self._request_type.m[self._name](**kwargs)
            )
        )
        if response.error is not None:
            raise utils.select(response.error)[1]
        else:
            return getattr(response.result, self._name)
