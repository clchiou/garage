"""Closable queues.

NOTE: These queues cannot be used among threads.
"""

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

from g1.bases import classes

from . import locks


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
        self.__getter_gate = locks.Gate()
        self.__putter_gate = locks.Gate()
        self.__closed = False

    __repr__ = classes.make_repr(
        '{state}, capacity={self.capacity}, size={size}',
        state=lambda self: 'closed' if self.__closed else 'open',
        size=len,
    )

    def __bool__(self):
        return bool(self.__queue)

    def __len__(self):
        """Return the size, not the capacity, of the queue."""
        return len(self.__queue)

    def is_full(self):
        """True if size is equal to or greater than capacity."""
        return self.capacity > 0 and len(self.__queue) >= self.capacity

    def is_closed(self):
        return self.__closed

    def close(self, graceful=True):
        """Close the queue.

        When ``graceful`` is false, it will drop and return all the
        queued items.  The caller may use this opportunity to properly
        release them.

        When ``close`` is called at multiple places, the first call site
        with ``graceful=False`` has the dropped items.
        """
        if graceful:
            items = []
        else:
            # Drop all items on non-graceful close.
            items, self.__queue = list(self.__queue), ()
        self.__closed = True
        self.__getter_gate.unblock()
        self.__putter_gate.unblock()
        return items

    async def get(self):
        """Get an item from the queue.

        If the queue is closed and empty, ``get`` raises ``Closed``.
        """
        while not self.__queue and not self.__closed:
            await self.__getter_gate.wait()
        return self.get_nonblocking()

    def get_nonblocking(self):
        if self.__queue:
            self.__putter_gate.unblock()
            return self.__get(self.__queue)
        elif self.__closed:
            raise Closed
        else:
            raise Empty

    async def put(self, item):
        """Put an item into the queue.

        If the queue is closed, ``put`` raises ``Closed``.
        """
        while True:
            try:
                return self.put_nonblocking(item)
            except Full:
                await self.__putter_gate.wait()

    def put_nonblocking(self, item):
        if self.__closed:
            raise Closed
        elif self.is_full():
            raise Full
        else:
            self.__getter_gate.unblock()
            self.__put(self.__queue, item)


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
