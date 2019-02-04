"""Closable queues."""

__all__ = [
    'Closed',
    'Empty',
    'Full',
    # Queue classes.
    'LifoQueue',
    'PriorityQueue',
    'Queue',
]

import collections
import heapq
import sys
import threading

from g1.bases import timers
from g1.bases.assertions import ASSERT

# Since version 3.2, Condition.wait returns False on timeout, and we
# depend on this semantics.
ASSERT.greater_or_equal(sys.version_info, (3, 2))


class Closed(Exception):
    pass


class Empty(Exception):
    pass


class Full(Exception):
    pass


class QueueBase:

    def __init__(self, capacity, queue, get, put):
        self.capacity = capacity
        self.__queue = queue
        self.__get = get
        self.__put = put
        self.__lock = threading.Lock()
        self.__not_empty = threading.Condition(self.__lock)
        self.__not_full = threading.Condition(self.__lock)
        self.__closed = False

    def __repr__(self):
        return '<%s at %#x: %s, capacity=%d, size=%d>' % (
            self.__class__.__qualname__,
            id(self),
            'closed' if self.__closed else 'open',
            self.capacity,
            len(self),
        )

    def __bool__(self):
        with self.__lock:
            return bool(self.__queue)

    def __len__(self):
        """Return the size, not the capacity, of the queue."""
        with self.__lock:
            return len(self.__queue)

    def is_full(self):
        """True if size is equal to or greater than capacity."""
        with self.__lock:
            return self.capacity > 0 and len(self.__queue) >= self.capacity

    def is_closed(self):
        with self.__lock:
            return self.__closed

    def close(self, graceful=True):
        """Close the queue.

        When ``graceful`` is false, it will drop and return all the
        queued items.  The caller may use this opportunity to properly
        release them.

        After the queue is closed, further calling ``close`` is no-op.
        """
        with self.__lock:
            if self.__closed:
                return []  # This is no-op.
            if graceful:
                items = []
            else:
                # Drop all items on non-graceful close.
                items, self.__queue = list(self.__queue), ()
            self.__closed = True
            self.__not_empty.notify_all()
            self.__not_full.notify_all()
            return items

    def get(self, timeout=None):
        """Get an item from the queue.

        If the queue is closed and empty, ``get`` raises ``Closed``.
        """
        with self.__not_empty:
            timer = timers.make(timeout)
            keep_waiting = True
            while True:
                if self.__queue:
                    break
                if self.__closed:
                    raise Closed
                if not keep_waiting:
                    raise Empty
                keep_waiting = self.__not_empty.wait(timer.get_timeout())
            item = self.__get(self.__queue)
            self.__not_full.notify()
            return item

    def put(self, item, timeout=None):
        """Put an item into the queue.

        If the queue is closed, ``put`` raises ``Closed``.
        """
        with self.__not_full:
            if self.__closed:
                raise Closed
            if self.capacity > 0:
                timer = timers.make(timeout)
                keep_waiting = True
                while True:
                    if self.__closed:
                        raise Closed
                    if len(self.__queue) < self.capacity:
                        break
                    if not keep_waiting:
                        raise Full
                    keep_waiting = self.__not_full.wait(timer.get_timeout())
            self.__put(self.__queue, item)
            self.__not_empty.notify()


#
# Concrete queue classes.
#


class Queue(QueueBase):

    def __init__(self, capacity=0):
        super().__init__(
            capacity,
            collections.deque(),
            collections.deque.popleft,
            collections.deque.append,
        )


class PriorityQueue(QueueBase):

    def __init__(self, capacity=0):
        super().__init__(
            capacity,
            [],
            heapq.heappop,
            heapq.heappush,
        )


class LifoQueue(QueueBase):

    def __init__(self, capacity=0):
        super().__init__(
            capacity,
            collections.deque(),
            collections.deque.pop,
            collections.deque.append,
        )