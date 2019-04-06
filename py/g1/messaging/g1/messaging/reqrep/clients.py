__all__ = [
    'Client',
]

import functools

import nng
import nng.asyncs

from g1.bases import classes
from g1.bases.assertions import ASSERT
from g1.bases.collections import Namespace


class Client:

    def __init__(self, request_type, response_type, wiredata):
        self._response_type = response_type
        self._wiredata = wiredata
        # You may (optionally) use context to close socket on exit.
        self.socket = nng.asyncs.Socket(nng.Protocols.REQ0)
        self.m = _make_transceivers(self, request_type)

    __repr__ = classes.make_repr('{self.socket!r}')

    def __enter__(self):
        self.socket.__enter__()
        return self

    def __exit__(self, *args):
        return self.socket.__exit__(*args)

    async def transceive(self, request):
        with nng.asyncs.Context(ASSERT.not_none(self.socket)) as context:
            await context.send(self._wiredata.to_lower(request))
            wire_response = await context.recv()
            return self._wiredata.to_upper(self._response_type, wire_response)

    async def _transceive(self, make_request, **kwargs):
        response = await self.transceive(make_request(**kwargs))
        if response.error is not None:
            raise response.error
        return response.result


def _make_transceivers(self, request_type):
    return Namespace(
        **{
            name: functools.partial(
                self._transceive,
                getattr(request_type, name),
            )
            for name in request_type._types
        }
    )
