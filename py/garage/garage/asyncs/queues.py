"""Closable queues."""

__all__ = [
    'Closed',
    'Empty',
    'Full',
    'Queue',
    'ZeroQueue',
]

import collections

import curio

from garage import asserts
from garage.threads.queues import Closed, Empty, Full


class QueueBase:
    """Abstract base class of queues."""

    ### Concrete queue classes must implement these three methods

    def _make(self, capacity):
        """Make the concrete queue data structure."""
        raise NotImplementedError

    def _get(self, queue):
        """Get an element from the concrete queue."""
        raise NotImplementedError

    def _put(self, queue, item):
        """Put an element into the concrete queue."""
        raise NotImplementedError

    def _to_list(self, queue):
        """Convert queue to list."""
        raise NotImplementedError

    ### QueueBase implementation starts here

    def __init__(self, capacity=0):
        self.__capacity = capacity
        self.__closed = curio.Event()
        # Use Event rather than Condition so that close() could be
        # non-async; the drawback is that every time we will wake up all
        # waiters (with Condition you may just notify one).
        self.__has_item = curio.Event()
        self.__has_vacancy = curio.Event()
        self.__has_vacancy.set()
        # Call subclass method last
        self.__queue = self._make(self.__capacity)

    def __bool__(self):
        return bool(self.__queue)

    def __len__(self):
        return len(self.__queue)

    def is_empty(self):
        return not self.__queue

    def is_full(self):
        return self.__capacity > 0 and len(self.__queue) >= self.__capacity

    def is_closed(self):
        return self.__closed.is_set()

    async def until_closed(self, raises=Closed):
        """Wait until the queue is closed."""
        await self.__closed.wait()
        if raises:
            raise raises

    def close(self, graceful=True):
        if self.is_closed():
            return []
        if graceful:
            items = []
        else:  # Drain the queue
            items, self.__queue = self._to_list(self.__queue), ()
        self.__closed.set()
        # Wake up all waiters
        self.__has_item.set()
        self.__has_vacancy.set()
        return items

    async def get(self):
        while self.is_empty():
            if self.is_closed():
                raise Closed
            asserts.precond(not self.__has_item.is_set())
            await self.__has_item.wait()
        return self.get_nowait()

    async def put(self, item):
        while True:
            if self.is_closed():
                raise Closed
            if not self.is_full():
                break
            asserts.precond(not self.__has_vacancy.is_set())
            await self.__has_vacancy.wait()
        self.put_nowait(item)

    # It's better not to add block=False argument to get() and have a
    # separate get_nowait() so that get_nowait() may be non-async (same
    # rationale applies to put_nowait, too).

    def get_nowait(self):
        """Non-blocking version of get()."""
        if self.is_empty():
            if self.is_closed():
                raise Closed
            raise Empty
        asserts.precond(self.__has_item.is_set())
        item = self._get(self.__queue)
        self.__has_vacancy.set()
        if self.is_empty():
            self.__has_item.clear()
        return item

    def put_nowait(self, item):
        """Non-blocking version of put()."""
        if self.is_closed():
            raise Closed
        if self.is_full():
            raise Full
        asserts.precond(self.__has_vacancy.is_set())
        self._put(self.__queue, item)
        self.__has_item.set()
        if self.is_full():
            self.__has_vacancy.clear()


class Queue(QueueBase):

    def _make(self, capacity):
        return collections.deque()

    def _get(self, queue):
        return queue.popleft()

    def _put(self, queue, item):
        queue.append(item)

    def _to_list(self, queue):
        return list(queue)


class ZeroQueue:
    """A queue with zero capacity."""

    def __init__(self):
        self._closed = curio.Event()

    def __bool__(self):
        return False

    def __len__(self):
        return 0

    def is_empty(self):
        return True

    def is_full(self):
        return True

    def is_closed(self):
        return self._closed.is_set()

    async def until_closed(self, raises=Closed):
        await self._closed.wait()
        if raises:
            raise raises

    def close(self, graceful=True):
        self._closed.set()
        return []

    async def get(self):
        if self.is_closed():
            raise Closed
        await self.until_closed()

    async def put(self, item):
        if self.is_closed():
            raise Closed
        await self.until_closed()

    def get_nowait(self):
        if self.is_closed():
            raise Closed
        else:
            raise Empty

    def put_nowait(self, item):
        if self.is_closed():
            raise Closed
        else:
            raise Full
