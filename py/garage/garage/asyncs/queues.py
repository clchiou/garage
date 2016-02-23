"""Closable queues."""

__all__ = [
    'Closed',
    'Empty',
    'Full',
    'Queue',
]

import asyncio
import collections


class Closed(Exception):
    """Exception raised at put() and get() when the queue is closed."""
    pass


class Empty(Exception):
    """Exception raised at get_nowait() when queue is is empty."""
    pass


class Full(Exception):
    """Exception raised at put_nowait() when queue is is full."""
    pass


class QueueBase:

    def __init__(self, capacity=0, *, loop=None):
        self._capacity = capacity
        self._lock = asyncio.Lock(loop=loop)
        self._not_empty = asyncio.Condition(self._lock, loop=loop)
        self._not_full = asyncio.Condition(self._lock, loop=loop)
        self._closed = False
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

    def is_full(self):
        return self._capacity > 0 and len(self._queue) >= self._capacity

    def is_closed(self):
        return self._closed

    async def close(self, graceful=True):
        async with self._lock:
            if self._closed:
                return []
            if graceful:
                items = []
            else:  # Drain the queue.
                items, self._queue = list(self._queue), ()
            self._closed = True
            self._not_empty.notify_all()
            self._not_full.notify_all()
            return items

    async def put(self, item, block=True):
        async with self._not_full:
            if self._closed:
                raise Closed
            if self._capacity > 0:
                while True:
                    if self._closed:
                        raise Closed
                    if not self.is_full():
                        break
                    if not block:
                        raise Full
                    await self._not_full.wait()
            self._put(item)
            self._not_empty.notify()

    async def get(self, block=True):
        async with self._not_empty:
            while not self._queue:
                if self._closed:
                    raise Closed
                if not block:
                    raise Empty
                await self._not_empty.wait()
            item = self._get()
            self._not_full.notify()
            return item


class Queue(QueueBase):

    def _make(self, capacity):
        return collections.deque()

    def _get(self):
        return self._queue.popleft()

    def _put(self, item):
        self._queue.append(item)
