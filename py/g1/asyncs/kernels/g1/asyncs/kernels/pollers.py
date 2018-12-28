"""Pollers.

At the moment this module does not intend to abstract away details and
quirks of underlying polling mechanisms, as doing so could result in
either leaky abstraction or complicated interface.  Instead, this module
exposes the platform-specific polling mechanism to higher level.
Obviously this is not portable, but for now this disadvantage should be
acceptable.
"""

__all__ = [
    'ERROR_EVENTS',
    'Epoll',
]

import math
import select

from g1.bases.assertions import ASSERT

ERROR_EVENTS = select.EPOLLERR | select.EPOLLHUP | select.EPOLLRDHUP


class Epoll:

    READ = select.EPOLLIN | select.EPOLLRDHUP
    WRITE = select.EPOLLOUT

    def __init__(self):
        self._epoll = select.epoll()
        self._fds = set()
        self._closed_fds = []

    def __repr__(self):
        return '<%s at %#x: %s, fds=%r>' % (
            self.__class__.__qualname__,
            id(self),
            'closed' if self._epoll.closed else 'open',
            self._fds,
        )

    def __enter__(self):
        ASSERT.false(self._epoll.closed)
        return self

    def __exit__(self, *_):
        ASSERT.false(self._epoll.closed)
        self.close()

    def close(self):
        ASSERT.false(self._epoll.closed)
        self._epoll.close()
        self._fds.clear()

    def register(self, fd, events):
        ASSERT.false(self._epoll.closed)
        ASSERT.not_in(fd, self._fds)
        self._epoll.register(fd, events)
        self._fds.add(fd)

    def unregister(self, fd):
        ASSERT.false(self._epoll.closed)
        if fd in self._fds:
            self._epoll.unregister(fd)
            self._fds.discard(fd)

    def close_fd(self, fd):
        """Inform the poller that a file descriptor is closed.

        Sadly ``epoll`` automatically removes a closed file descriptor
        internally without informing the poller, and thus we need a way
        to inform the poller about this.
        """
        ASSERT.false(self._epoll.closed)
        self._closed_fds.append((fd, select.EPOLLHUP))

    def poll(self, timeout):
        ASSERT.false(self._epoll.closed)
        if self._closed_fds:
            closed_fds, self._closed_fds = self._closed_fds, []
            return closed_fds
        ASSERT.not_empty(self._fds)
        if timeout is None:
            timeout = -1
        elif timeout <= 0:
            timeout = 0
        else:
            # epoll_wait() has a resolution of 1 millisecond.
            timeout = math.ceil(timeout * 1e3) * 1e-3
        max_num_events = len(self._fds)
        try:
            return self._epoll.poll(timeout, max_num_events)
        except InterruptedError:
            return []
