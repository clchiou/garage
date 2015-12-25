__all__ = [
    'Watchdog',
]

import asyncio
import logging


LOG = logging.getLogger(__name__)


class Watchdog:

    def __init__(self, delay, callback, loop=None):
        self.delay = delay
        self.callback = callback
        self._loop = loop
        self._handle = None

    @property
    def started(self):
        return self._handle is not None

    @property
    def stopped(self):
        return self._handle is None

    @property
    def loop(self):
        return self._loop or asyncio.get_event_loop()

    def start(self):
        if self.started:
            return
        LOG.debug('start watchdog %r', self)
        self._handle = self.loop.call_later(self.delay, self._bark)

    def restart(self):
        if self.stopped:
            self.start()
        else:
            self._handle.cancel()
            self._handle = self.loop.call_later(self.delay, self._bark)

    def stop(self):
        if self.stopped:
            return
        LOG.debug('stop watchdog %r', self)
        self._handle.cancel()
        self._handle = None

    def _bark(self):
        LOG.debug('watchdog %r is barking at you', self)
        self.callback()
        self._handle = None
