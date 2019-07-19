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
        self._request_type = request_type
        self._response_type = response_type
        self._wiredata = wiredata
        # You may (optionally) use context to close socket on exit.
        self.socket = nng.asyncs.Socket(nng.Protocols.REQ0)
        self.m = collections.Namespace(
            **{name: _make_transceiver(self, name)
               for name in request_type.m}
        )

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


def _make_transceiver(self, name):

    make = self._request_type.m[name]

    async def transceive(**kwargs):
        response = await self.transceive(
            self._request_type(args=make(**kwargs))
        )
        if response.error is not None:
            raise utils.select(response.error)[1]
        else:
            return getattr(response.result, name)

    return transceive
