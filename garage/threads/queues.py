"""Closable and thread-safe queues.

These queues are modeled after standard library's queue module.
"""

__all__ = [
    'Closed',
    'Empty',
    'Full',
    'Queue',
    'PriorityQueue',
    'LifoQueue',
]

import collections
import heapq
import time
import threading
from queue import Empty
from queue import Full


class Closed(Exception):
    """Exception raised by put() and get() when the queue is closed."""
    pass


class _QueueBase:

    def __init__(self, capacity):
        self._capacity = capacity
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._not_full = threading.Condition(self._lock)
        self._closed = False

    _queue = None

    def _put(self, _):
        raise NotImplementedError

    def _get(self):
        raise NotImplementedError

    def __bool__(self):
        with self._lock:
            return bool(self._queue)

    def __len__(self):
        """Return the size, not the capacity, of the queue."""
        with self._lock:
            return len(self._queue)

    def is_full(self):
        """True if size is equal to or greater than capacity."""
        with self._lock:
            return self._capacity > 0 and len(self._queue) >= self._capacity

    def is_closed(self):
        with self._lock:
            return self._closed

    def close(self, graceful=True):
        """Close the queue and return the items (if you need to release
           them).

           NOTE: All blocking put() and get() will raise Closed; so only
           call close() when you really have to.
        """
        with self._lock:
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

    def put(self, item, block=True, timeout=None):
        """Same as standard library's put() of queue module except that
           it will raise Closed in all blocked producer threads after
           the queue is being closed.
        """
        with self._not_full:
            if self._closed:
                raise Closed
            if self._capacity > 0:
                waiter = _make_waiter(block, timeout)
                waiter.send(self._not_full)
                keep_waiting = True
                while True:
                    if self._closed:
                        raise Closed
                    if len(self._queue) < self._capacity:
                        break
                    if not keep_waiting:
                        raise Full
                    try:
                        next(waiter)
                    except StopIteration:
                        keep_waiting = False
            self._put(item)
            self._not_empty.notify()

    def get(self, block=True, timeout=None):
        """Same as standard library's get() of queue module except that
           it will raise Closed in all blocked consumer threads after
           the queue is empty and is being closed.
        """
        with self._not_empty:
            waiter = _make_waiter(block, timeout)
            waiter.send(self._not_empty)
            keep_waiting = True
            while True:
                if self._queue:
                    break
                if self._closed:
                    raise Closed
                if not keep_waiting:
                    raise Empty
                try:
                    next(waiter)
                except StopIteration:
                    keep_waiting = False
            item = self._get()
            self._not_full.notify()
            return item


def _make_waiter(block, timeout):
    """Return a generator that calls Condition.wait.

       You first call waiter.send(cond) to give it a condition variable
       to wait for, and then every time you call next(waiter), it will
       either call Condition.wait or raise StopIteration.
    """
    if not block:
        waiter = _non_blocking()
    elif timeout is None:
        waiter = _blocking()
    else:
        if timeout < 0:
            raise ValueError('timeout must be non-negative')
        waiter = _blocking_timeout(timeout)
    next(waiter)
    return waiter


def _non_blocking():
    _ = yield
    yield


def _blocking():
    cond = yield
    while True:
        yield
        cond.wait()


def _blocking_timeout(timeout):
    cond = yield
    end_time = time.monotonic() + timeout
    while True:
        remaining = end_time - time.monotonic()
        if remaining <= 0.0:
            yield
            break
        yield
        cond.wait(remaining)


class Queue(_QueueBase):

    def __init__(self, capacity=0):
        super().__init__(capacity)
        self._queue = collections.deque()

    def _put(self, item):
        self._queue.append(item)

    def _get(self):
        return self._queue.popleft()


class PriorityQueue(_QueueBase):

    def __init__(self, capacity=0):
        super().__init__(capacity)
        self._queue = []

    def _put(self, item):
        heapq.heappush(self._queue, item)

    def _get(self):
        return heapq.heappop(self._queue)


class LifoQueue(_QueueBase):

    def __init__(self, capacity=0):
        super().__init__(capacity)
        self._queue = []

    def _put(self, item):
        self._queue.append(item)

    def _get(self):
        return self._queue.pop()
