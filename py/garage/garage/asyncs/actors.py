"""Asynchronous support for garage.threads.actors."""

__all__ = [
    'AsyncStub',
]

from garage.asyncs import futures
from garage.threads import actors


class AsyncStub(actors.Stub):

    def _get_future(self):
        return futures.FutureAdapter(super()._get_future())

    def _send_message(self, func, args, kwargs):
        """Enqueue a message into actor's message queue.

           NOTE: This does not block; meaning it could raise a Full
           exception when the message queue is full.
        """
        future = super()._send_message(func, args, kwargs, block=False)
        return futures.FutureAdapter(future)
