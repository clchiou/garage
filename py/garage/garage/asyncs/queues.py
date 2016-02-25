"""Closable queues."""

__all__ = [
    'Closed',
    'Empty',
    'Full',
    'Queue',
]

import asyncio
import collections

from garage import asserts


class Closed(Exception):
    """Exception raised at put() when the queue is closed, or at get()
       when the queue is empty and closed.
    """
    pass


class Empty(Exception):
    """Exception raised at get(block=False) when queue is empty but not
       closed.
    """
    pass


class Full(Exception):
    """Exception raised at put(block=False) when queue is full."""
    pass


class QueueBase:

    def __init__(self, capacity=0, *, loop=None):
        self._capacity = capacity
        self._closed = False
        # Use Event rather than Condition so that close() could be
        # non-async.
        self._has_item = asyncio.Event(loop=loop)
        self._has_vacancy = asyncio.Event(loop=loop)
        self._has_vacancy.set()
        # Call subclass method last.
        self._queue = self._make(self._capacity)

    def _make(self, capacity):
        raise NotImplementedError

    def _get(self):
        raise NotImplementedError

    def _put(self, item):
        raise NotImplementedError

    def __bool__(self):
        return bool(self._queue)

    def __len__(self):
        return len(self._queue)

    def is_empty(self):
        return not self._queue

    def is_full(self):
        return self._capacity > 0 and len(self._queue) >= self._capacity

    def is_closed(self):
        return self._closed

    def close(self, graceful=True):
        if self.is_closed():
            return []
        if graceful:
            items = []
        else:  # Drain the queue.
            items, self._queue = list(self._queue), ()
        self._closed = True
        # Wake up all waiters.
        self._has_item.set()
        self._has_vacancy.set()
        return items

    async def put(self, item, block=True):
        while True:
            if self.is_closed():
                raise Closed
            if not self.is_full():
                break
            if not block:
                raise Full
            asserts.precond(not self._has_vacancy.is_set())
            await self._has_vacancy.wait()
        asserts.postcond(self._has_vacancy.is_set())
        self._put(item)
        self._has_item.set()
        if self.is_full():
            self._has_vacancy.clear()

    async def get(self, block=True):
        while self.is_empty():
            if self.is_closed():
                raise Closed
            if not block:
                raise Empty
            asserts.precond(not self._has_item.is_set())
            await self._has_item.wait()
        asserts.postcond(self._has_item.is_set())
        item = self._get()
        self._has_vacancy.set()
        if self.is_empty():
            self._has_item.clear()
        return item


class Queue(QueueBase):

    def _make(self, capacity):
        return collections.deque()

    def _get(self):
        return self._queue.popleft()

    def _put(self, item):
        self._queue.append(item)
