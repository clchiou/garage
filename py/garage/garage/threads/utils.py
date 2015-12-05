__all__ = [
    'AtomicInt',
    'AtomicSet',
    'ExclusiveAccessor',
    'TaskQueue',
    'Priority',
    'generate_names',
    'make_get_thread_local',
]

import collections
import functools
import threading

from garage import asserts
from garage.threads import queues


class AtomicInt:

    def __init__(self, value=0):
        self._lock = threading.Lock()
        self._value = value

    def get_and_set(self, new_value):
        with self._lock:
            value = self._value
            self._value = new_value
            return value

    def get_and_add(self, add_to):
        with self._lock:
            value = self._value
            self._value += add_to
            return value


class AtomicSet:

    def __init__(self):
        self._lock = threading.Lock()
        self._items = set()

    def __contains__(self, item):
        with self._lock:
            return item in self._items

    def check_and_add(self, item):
        with self._lock:
            has_item = item in self._items
            if not has_item:
                self._items.add(item)
            return has_item


class ExclusiveAccessor:

    def __init__(self, resource, lock=None):
        self._resource = resource
        self._lock = lock or threading.RLock()

    def __enter__(self):
        self._lock.acquire()
        return self._resource

    def __exit__(self, *_):
        self._lock.release()


class TaskQueue(queues.ForwardingQueue):
    """A one-time use task queue.

       Tasks are in one of the three states in progression of their
       lifetime:

       * QUEUED: When a task is queued.

       * PROCESSING: A worker is processing this task.

       * PROCESSED: A worker is done processing this task, regardless
         the task succeeded or failed.

       After all tasks have been processed, the task queue will close
       itself automatically (and thus it is one-time use only).

       You may use this auto-close feature to wait for the completion of
       all tasks.
    """

    def notify_task_processed(self):
        """Notify the queue that a task has been processed."""
        with self.lock:
            if not self:
                self.close()


@functools.total_ordering
class Priority:
    """A wrapper class that supports lowest/highest priority sentinels,
       which should be handy when used with Python's heap.

       This is an immutable value class.

       NOTE: Python's heap[0] is the smallest item; so we will have the
       highest priority be the smallest.
    """

    def __init__(self, priority):
        asserts.precond(isinstance(priority, collections.Hashable))
        self._priority = priority

    def __str__(self):
        if self is Priority.LOWEST:
            return 'Priority.LOWEST'
        elif self is Priority.HIGHEST:
            return 'Priority.HIGHEST'
        else:
            return 'Priority(%r)' % (self._priority,)

    __repr__ = __str__

    def __hash__(self):
        return hash(self._priority)

    def __eq__(self, other):
        return self._priority == other._priority

    def __lt__(self, other):
        # NOTE: Smaller = higher priority!

        decision = {
            (True, True): False,
            (True, False): False,
            (False, True): True,
            (False, False): None,
        }[self is Priority.LOWEST, other is Priority.LOWEST]
        if decision is not None:
            return decision

        decision = {
            (True, True): False,
            (True, False): True,
            (False, True): False,
            (False, False): None,
        }[self is Priority.HIGHEST, other is Priority.HIGHEST]
        if decision is not None:
            return decision

        return self._priority < other._priority


Priority.LOWEST = Priority(object())
Priority.HIGHEST = Priority(object())


def generate_names(name_format='{name}-{serial:02d}', **kwargs):
    """Useful for generate names of an actor with a serial number."""
    serial = kwargs.pop('serial', None) or AtomicInt(1)
    while True:
        yield name_format.format(serial=serial.get_and_add(1), **kwargs)


def make_get_thread_local(make):
    local = threading.local()
    def get_thread_local():
        if not hasattr(local, 'obj'):
            local.obj = make()
        return local.obj
    return get_thread_local
