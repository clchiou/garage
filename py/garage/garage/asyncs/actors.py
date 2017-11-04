"""Asynchronous support for garage.threads.actors."""

__all__ = [
    'StubAdapter',
]

from garage.asyncs import futures


class StubAdapter:
    """Wrap all method calls, adding FutureAdapter on their result.

    While this simple adapter does not work for all corner cases, for
    common cases, it should work fine.
    """

    def __init__(self, stub):
        self._stub = stub

    def __getattr__(self, name):
        method = getattr(self._stub, name)
        # Simple foolproof detection of non-message-sending access.
        if name.startswith('_'):
            return method
        return lambda *args, **kwargs: \
            futures.FutureAdapter(method(*args, **kwargs))

    def _get_future(self):
        return futures.FutureAdapter(self._stub._get_future())

    def _send_message(self, func, args, kwargs):
        """Enqueue a message into actor's message queue.

        Since this does not block, it may raise Full when the message
        queue is full.
        """
        future = self._stub._send_message(func, args, kwargs, block=False)
        return futures.FutureAdapter(future)

    async def _kill_and_join(self, graceful=True):
        self._kill(graceful=graceful)
        await self._get_future().result()
