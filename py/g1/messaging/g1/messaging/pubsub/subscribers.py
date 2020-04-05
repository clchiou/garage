__all__ = [
    'Subscriber',
]

import logging

import nng
import nng.asyncs

from g1.asyncs.bases import queues
from g1.bases import classes

LOG = logging.getLogger(__name__)


class Subscriber:

    def __init__(self, message_type, queue, wiredata, *, drop_when_full=True):
        self._message_type = message_type
        self._queue = queue
        self._wiredata = wiredata
        self._drop_when_full = drop_when_full
        # For convenience, create socket before ``__enter__``.
        self.socket = nng.asyncs.Socket(nng.Protocols.SUB0)
        # For now we subscribe to empty topic.
        self.socket.subscribe(b'')

    __repr__ = classes.make_repr('{self.socket!r}')

    def __enter__(self):
        self.socket.__enter__()
        return self

    def __exit__(self, exc_type, *args):
        messages = self._queue.close(graceful=not exc_type)
        if messages:
            LOG.warning('drop %d messages', len(messages))
        return self.socket.__exit__(exc_type, *args)

    async def serve(self):
        LOG.info('start subscriber: %r', self)
        try:
            while True:
                try:
                    raw_message = await self.socket.recv()
                except nng.Errors.ETIMEDOUT:
                    LOG.warning('recv timeout')
                    continue
                try:
                    message = self._wiredata.to_upper(
                        self._message_type, raw_message
                    )
                except Exception:
                    LOG.warning(
                        'to_upper error: %r', raw_message, exc_info=True
                    )
                    continue
                if self._drop_when_full:
                    try:
                        self._queue.put_nonblocking(message)
                    except queues.Full:
                        LOG.warning('queue full; drop message: %r', message)
                else:
                    await self._queue.put(message)
        except (queues.Closed, nng.Errors.ECLOSED):
            pass
        self._queue.close()
        LOG.info('stop subscriber: %r', self)

    def shutdown(self):
        self.socket.close()
