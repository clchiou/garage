"""Asynchronous support for garage.threads.actors."""

__all__ = [
    'AsyncStub',
]

from garage.asyncs import futures
from garage.threads import actors


class AsyncStub(actors.Stub):

    def get_future(self):
        return futures.FutureAdapter(super().get_future())

    def send_message(self, func, args, kwargs):
        """Enqueue a message into actor's message queue.

           NOTE: This does not block; meaning it could raise a Full
           exception when the message queue is full.
        """
        future = super().send_message(func, args, kwargs, block=False)
        return futures.FutureAdapter(future)
