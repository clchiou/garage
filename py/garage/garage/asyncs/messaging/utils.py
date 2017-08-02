__all__ = [
    'ClientBase',
]

import capnp

from garage.asyncs import futures
from garage.asyncs import queues
from garage.asyncs.messaging import reqrep


class ClientBase:
    """Abstract base class for implementing reqrep client."""

    def _parse_response(self, request, response_struct):
        """Parse response object (and may raise error)."""
        raise NotImplementedError

    def __init__(self, request_queue, *, packed=False):
        self.__request_queue = request_queue
        if packed:
            self.__from_bytes = capnp.MessageReader.from_packed_bytes
            self.__to_bytes = capnp.MessageBuilder.to_packed_bytes
        else:
            self.__from_bytes = capnp.MessageReader.from_bytes
            self.__to_bytes = capnp.MessageBuilder.to_bytes

    async def _transact(self, request):
        """Make a transaction.

        This is intended to be called by subclass.
        """

        raw_request = self.__to_bytes(request._message)

        async with futures.Future() as raw_resposne_future:

            try:
                await self.__request_queue.put((
                    raw_request,
                    raw_resposne_future.promise(),
                ))
            except queues.Closed:
                raise reqrep.Terminated from None

            raw_response = await raw_resposne_future.result()

        return self._parse_response(
            request,
            self.__from_bytes(raw_response),
        )
