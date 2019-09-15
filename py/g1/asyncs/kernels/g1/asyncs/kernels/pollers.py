"""Pollers.

At the moment this module does not intend to abstract away details and
quirks of underlying polling mechanisms, as doing so could result in
either leaky abstraction or complicated interface.  Instead, this module
exposes the platform-specific polling mechanism to higher level.
Obviously this is not portable, but for now this disadvantage should be
acceptable.
"""

__all__ = [
    'Epoll',
]

import math
import select

from g1.bases import classes
from g1.bases.assertions import ASSERT


class Epoll:

    READ = select.EPOLLIN
    WRITE = select.EPOLLOUT
    EDGE_TRIGGER = select.EPOLLET

    def __init__(self):
        self._epoll = select.epoll()
        self._events = {}
        self._closed_fds = []

    __repr__ = classes.make_repr(
        '{state} events={self._events}',
        state=lambda self: 'closed' if self._epoll.closed else 'open',
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
        self._events.clear()

    def register(self, fd, events):
        ASSERT.false(self._epoll.closed)
        if fd in self._events:
            previous_events = self._events[fd]
            self._events[fd] |= events
            if previous_events != self._events[fd]:
                self._epoll.modify(fd, self._events[fd])
        else:
            self._events[fd] = events
            self._epoll.register(fd, self._events[fd])

    def close_fd(self, fd):
        """Inform the poller that a file descriptor is closed.

        Sadly ``epoll`` silently removes a closed file descriptor
        internally without informing the poller, and thus we need a way
        to inform the poller about this.
        """
        ASSERT.false(self._epoll.closed)
        if fd not in self._events:
            return
        self._epoll.unregister(fd)
        event = self._events.pop(fd)
        self._closed_fds.append((fd, event | select.EPOLLHUP))

    def poll(self, timeout):
        ASSERT.false(self._epoll.closed)
        if self._closed_fds:
            closed_fds, self._closed_fds = self._closed_fds, []
            return closed_fds
        ASSERT.not_empty(self._events)
        if timeout is None:
            timeout = -1
        elif timeout <= 0:
            timeout = 0
        else:
            # epoll_wait() has a resolution of 1 millisecond.
            timeout = math.ceil(timeout * 1e3) * 1e-3
        try:
            return self._epoll.poll(timeout=timeout)
        except InterruptedError:
            return []
