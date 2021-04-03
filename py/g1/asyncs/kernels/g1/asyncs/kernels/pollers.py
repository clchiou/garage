__all__ = [
    'Poller',
    'Polls',
    # Poller implementations.
    #
    # TODO: Only epoll is supported as cross-platform is not priority.
    'Epoll',
]

import enum
import errno
import math
import select
import threading
from typing import Sequence, Tuple, Union

from g1.bases.assertions import ASSERT


class Polls(enum.Enum):
    """Type of polls.

    A task may either read or write a file, but never both at the same
    time (at least I can't think of a use case of that).
    """
    READ = enum.auto()
    WRITE = enum.auto()


class Poller:

    def close(self):
        """Close the poller."""
        raise NotImplementedError

    def notify_open(self, fd: int):
        """Add the given file descriptor to the poller."""
        raise NotImplementedError

    def notify_close(self, fd: int):
        """Remove the given file descriptor from the poller.

        NOTE: This might be called in another thread.
        """
        raise NotImplementedError

    def poll(
        self,
        timeout: Union[float, None],
    ) -> Tuple[Sequence[int], Sequence[int]]:
        """Poll and return readable and writeable file descriptors.

        NOTE: This could return extra file descriptors, like write-end
        of pipes as readable file descriptors.
        """
        raise NotImplementedError


class Epoll(Poller):

    _EVENT_MASK = (
        select.EPOLLIN | select.EPOLLOUT | select.EPOLLET | select.EPOLLRDHUP
    )

    # Add EPOLLHUP, EPOLLRDHUP, EPOLLERR to the mask.  This should
    # unblock all tasks whenever a file is readable or writeable, at the
    # cost of (rare?) spurious wakeup or "extra" file descriptors.
    _EVENT_IN = (
        select.EPOLLIN | select.EPOLLHUP | select.EPOLLRDHUP | select.EPOLLERR
    )
    _EVENT_OUT = (
        select.EPOLLOUT | select.EPOLLHUP | select.EPOLLRDHUP | select.EPOLLERR
    )

    def __init__(self):
        self._lock = threading.Lock()
        self._epoll = select.epoll()
        self._closed_fds = set()

    def close(self):
        self._epoll.close()

    def notify_open(self, fd):
        ASSERT.false(self._epoll.closed)
        try:
            self._epoll.register(fd, self._EVENT_MASK)
        except FileExistsError:
            pass

    def notify_close(self, fd):
        ASSERT.false(self._epoll.closed)
        with self._lock:
            self._closed_fds.add(fd)
        try:
            self._epoll.unregister(fd)
        except OSError as exc:
            if exc.errno != errno.EBADF:
                raise

    def poll(self, timeout):
        ASSERT.false(self._epoll.closed)

        with self._lock:
            if self._closed_fds:
                closed_fds, self._closed_fds = self._closed_fds, set()
                return closed_fds, closed_fds

        if timeout is None:
            pass
        elif timeout <= 0:
            timeout = 0
        else:
            # epoll_wait() has a resolution of 1 millisecond.
            timeout = math.ceil(timeout * 1e3) * 1e-3

        can_read = []
        can_write = []
        # Since Python 3.5, poll retries with a re-computed timeout
        # rather than raising InterruptedError (see PEP 475).
        for fd, events in self._epoll.poll(timeout=timeout):
            if events & self._EVENT_IN:
                can_read.append(fd)
            if events & self._EVENT_OUT:
                can_write.append(fd)

        return can_read, can_write
