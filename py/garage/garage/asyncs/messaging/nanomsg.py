__all__ = [
    'device',
]

import warnings

import nanomsg as nn

from garage.asyncs.actors import StubAdapter
from garage.threads.actors import OneShotActor


_make_device = OneShotActor.from_func(nn.device)


async def device(socket1, socket2):
    stub = StubAdapter(_make_device(socket1, socket2))
    future = stub._get_future()
    try:
        #
        # XXX If this raises TaskCancelled, what should we do then?  The
        # only way to stop the actor thread is to call nn.terminate.  At
        # the moment we merely warn the caller.
        #
        await future.result()
    except (nn.EBADF, nn.ETERM):
        pass
    finally:
        if not future.done():
            warnings.warn('actor %s is still running', stub._name)
