__all__ = [
    'Publisher',
]

import logging

import nng
import nng.asyncs

from g1.asyncs.bases import queues
from g1.bases import classes

LOG = logging.getLogger(__name__)


class Publisher:

    def __init__(self, queue, wiredata, *, drop_when_full=True):
        self._queue = queue
        self._wiredata = wiredata
        self._drop_when_full = drop_when_full
        # For convenience, create socket before ``__enter__``.
        self.socket = nng.asyncs.Socket(nng.Protocols.PUB0)

    __repr__ = classes.make_repr('{self.socket!r}')

    def __enter__(self):
        self.socket.__enter__()
        return self

    def __exit__(self, *args):
        messages = self._queue.close(graceful=False)
        if messages:
            LOG.warning('drop %d messages', len(messages))
        return self.socket.__exit__(*args)

    async def serve(self):
        LOG.info('start publisher: %r', self)
        try:
            while True:
                message = await self._queue.get()
                try:
                    raw_message = self._wiredata.to_lower(message)
                except Exception:
                    LOG.exception('to_lower error: %r', message)
                    continue
                try:
                    # For now we publish with no topic.
                    await self.socket.send(raw_message)
                except nng.Errors.ETIMEDOUT:
                    LOG.warning('send timeout; drop message: %r', message)
                    continue
        except (queues.Closed, nng.Errors.ECLOSED):
            pass
        self._queue.close()
        LOG.info('stop publisher: %r', self)

    def shutdown(self):
        self._queue.close()

    async def publish(self, message):
        await self._queue.put(message)

    def publish_nonblocking(self, message):
        try:
            self._queue.put_nonblocking(message)
        except queues.Full:
            if self._drop_when_full:
                LOG.warning('queue full; drop message: %r', message)
            else:
                raise
