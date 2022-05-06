__all__ = [
    'DictBlocker',
    'ForeverBlocker',
    'TaskCompletionBlocker',
    'TimeoutBlocker',
]

import heapq

from g1.bases.assertions import ASSERT

from . import tasks


class BlockerBase:
    """Abstract blocker interface.

    This tracks which-task-is-blocked-by-what relationship.
    """

    def __bool__(self):
        raise NotImplementedError

    def __len__(self):
        raise NotImplementedError

    def __iter__(self):
        raise NotImplementedError

    def block(self, source, task):
        """Register that ``task`` is blocked by ``source``."""
        raise NotImplementedError

    def unblock(self, source):
        """Unblock all ``task`` blocked by ``source``.

        Return all unblocked tasks.
        """
        raise NotImplementedError

    def cancel(self, task):
        """Cancel blocking on ``task``.

        Return source or true if ``task`` actually cancelled.
        """
        raise NotImplementedError


class ForeverBlocker(BlockerBase):
    """Blocker that never unblocks."""

    def __init__(self):
        self._tasks = set()

    def __bool__(self):
        return bool(self._tasks)

    def __len__(self):
        return len(self._tasks)

    def __iter__(self):
        return iter(self._tasks)

    def block(self, source, task):
        del source  # Unused.
        self._tasks.add(task)

    def unblock(self, source):
        return ()

    def cancel(self, task):
        if task in self._tasks:
            self._tasks.remove(task)
            return True
        else:
            return False


class DictBlocker(BlockerBase):
    """Blocker implemented by ``dict``.

    NOTE: It cannot track a task being blocked by more than one source.
    """

    def __init__(self):
        self._task_to_source = {}
        # Reverse look-up table for faster ``unblock``.
        self._source_to_tasks = {}

    def __bool__(self):
        return bool(self._task_to_source)

    def __len__(self):
        return len(self._task_to_source)

    def __iter__(self):
        return iter(self._task_to_source)

    def block(self, source, task):
        ASSERT.not_none(source)
        ASSERT.not_in(task, self._task_to_source)
        self._task_to_source[task] = source
        # Update reverse look-up table.
        lookup = self._source_to_tasks.get(source)
        if lookup is None:
            lookup = self._source_to_tasks[source] = set()
        lookup.add(task)

    def unblock(self, source):
        lookup = self._source_to_tasks.pop(source, ())
        for task in lookup:
            self._task_to_source.pop(task)
        return lookup

    def cancel(self, task):
        source = self._task_to_source.pop(task, None)
        if source is not None:
            lookup = self._source_to_tasks[source]
            lookup.discard(task)
            if not lookup:
                self._source_to_tasks.pop(source)
        return source


class TaskCompletionBlocker(DictBlocker):
    """Track all tasks blocked in ``join`` calls."""

    def block(self, source, task):
        """Record that ``task`` is joining on ``source`` task."""
        ASSERT.isinstance(source, tasks.Task)
        ASSERT.is_not(source, task)  # A task can't join on itself.
        ASSERT.false(source.is_completed())
        return super().block(source, task)


class TimeoutBlocker(BlockerBase):

    class Item:

        __slots__ = ('source', 'task')

        def __init__(self, source, task):
            self.source = source
            self.task = task

        def __lt__(self, other):
            return self.source < other.source

    def __init__(self):
        self._tasks = set()
        self._queue = []

    def __bool__(self):
        return bool(self._tasks)

    def __len__(self):
        return len(self._tasks)

    def __iter__(self):
        return iter(self._tasks)

    def block(self, source, task):
        ASSERT.isinstance(source, (int, float))
        ASSERT.not_in(task, self._tasks)
        heapq.heappush(self._queue, self.Item(source, task))
        self._tasks.add(task)

    def unblock(self, source):
        unblocked = []
        while self._queue and self._queue[0].source <= source:
            task = heapq.heappop(self._queue).task
            if task in self._tasks:
                unblocked.append(task)
            self._tasks.discard(task)
        return unblocked

    def cancel(self, task):
        if task in self._tasks:
            self._tasks.discard(task)
            return True
        else:
            return False

    def get_min_timeout(self, now):
        if self._queue:
            return self._queue[0].source - now
        else:
            return None
