"""Utilities for external users."""

__all__ = [
    'Closed',
    'TaskCompletionQueue',
]

import collections
import logging

from . import errors
from . import locks

LOG = logging.getLogger(__name__)


class Closed(Exception):
    pass


class TaskCompletionQueue:
    """Provide queue-like interface on waiting for task completion.

    NOTE: It does not support future objects; this simplifies its
    implementation, and thus may be more efficient.
    """

    def __init__(self):
        self._event = locks.Event()
        self._completed = collections.deque()
        self._uncompleted = set()
        self._closed = False

    def __repr__(self):
        return '<%s at %#x: %s, completed=%d, uncompleted=%d>' % (
            self.__class__.__qualname__,
            id(self),
            'closed' if self._closed else 'open',
            len(self._completed),
            len(self._uncompleted),
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, *_):
        """Reasonable default policy on joining tasks.

        * First, it will close the queue.
        * On normal exit, it will join all remaining tasks.
        * On error, it will cancel tasks before joining them.

        This is not guaranteed to fit any use case though.  On those
        cases, you will have to roll your own context manager.
        """
        # Do not call close with ``graceful=False`` to get the remaining
        # tasks because the queue might have been closed already.
        self.close()
        tasks = self._move_tasks()
        if exc_type:
            for task in tasks:
                task.cancel()
        for task in tasks:
            exc = await task.get_exception()
            if not exc:
                pass
            elif isinstance(exc, errors.Cancelled):
                LOG.warning('task is cancelled: %r', task, exc_info=exc)
            else:
                LOG.error('task error: %r', task, exc_info=exc)

    def is_closed(self):
        return self._closed

    def __bool__(self):
        return bool(self._completed) or bool(self._uncompleted)

    def __len__(self):
        return len(self._completed) + len(self._uncompleted)

    def close(self, graceful=True):
        if self._closed:
            return []
        if graceful:
            tasks = []
        else:
            tasks = self._move_tasks()
        self._closed = True
        self._event.set()  # Notify all waiters on close.
        return tasks

    def _move_tasks(self):
        tasks = list(self._completed)
        tasks.extend(self._uncompleted)
        self._completed.clear()
        self._uncompleted.clear()
        return tasks

    async def get(self):
        while True:
            if self._completed:
                return self._completed.popleft()
            elif self._uncompleted or not self._closed:
                self._event.clear()
                await self._event.wait()
            else:
                raise Closed

    async def as_completed(self):
        while True:
            try:
                yield await self.get()
            except Closed:
                break

    def put(self, task):
        if self._closed:
            raise Closed
        self._uncompleted.add(task)
        task.add_callback(self._on_completion)

    def _on_completion(self, task):
        if self._uncompleted:
            self._uncompleted.remove(task)
            self._completed.append(task)
        self._event.set()
