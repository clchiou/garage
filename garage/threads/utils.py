__all__ = [
    'AtomicInt',
    'AtomicSet',
    'TaskQueue',
    'Priority',
    'generate_names',
]

import functools
import threading
from concurrent import futures

from garage.threads import queues


class AtomicInt:

    def __init__(self, value=0):
        self._lock = threading.Lock()
        self._value = value

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
       all tasks.  To make this even easier, a Future object is set for
       this purpose.
    """

    def __init__(self, queue):
        super().__init__(queue)
        self.future = futures.Future()
        self.future.set_running_or_notify_cancel()

    def notify_task_processed(self):
        """Notify the queue that a task has been processed."""
        with self.lock:
            if not self:
                self.close()

    def close(self, graceful=True):
        with self.lock:
            self.future.set_result(None)
            return super().close(graceful)


@functools.total_ordering
class Priority:
    """A wrapper class of the underlying priority object that implements
       comparison with lowest/highest priority sentinels.

       The underlying priority object has to support __lt__ and __eq__
       at very least.

       This class might be handy when you are using a priority queue.
    """

    def __init__(self, priority):
        self.priority = priority

    def __str__(self):
        if self is Priority.LOWEST:
            return 'Priority.LOWEST'
        elif self is Priority.HIGHEST:
            return 'Priority.HIGHEST'
        else:
            return 'Priority(%r)' % (self.priority,)

    __repr__ = __str__

    def __lt__(self, other):
        decision = {
            (True, True): False,
            (True, False): True,
            (False, True): False,
            (False, False): None,
        }[(self.priority is Priority.LOWEST,
           other.priority is Priority.LOWEST)]
        if decision is not None:
            return decision

        decision = {
            (True, True): False,
            (True, False): False,
            (False, True): True,
            (False, False): None,
        }[(self.priority is Priority.HIGHEST,
           other.priority is Priority.HIGHEST)]
        if decision is not None:
            return decision

        return self.priority < other.priority

    def __eq__(self, other):
        decision = {
            (True, True): True,
            (True, False): False,
            (False, True): False,
            (False, False): None,
        }[(self.priority is Priority.LOWEST,
           other.priority is Priority.LOWEST)]
        if decision is not None:
            return decision

        decision = {
            (True, True): True,
            (True, False): False,
            (False, True): False,
            (False, False): None,
        }[(self.priority is Priority.HIGHEST,
           other.priority is Priority.HIGHEST)]
        if decision is not None:
            return decision

        return self.priority == other.priority

    def __hash__(self):
        if self is Priority.LOWEST or self is Priority.HIGHEST:
            return id(self)
        else:
            return hash(self.priority)


Priority.LOWEST = Priority(None)
Priority.LOWEST.priority = Priority.LOWEST


Priority.HIGHEST = Priority(None)
Priority.HIGHEST.priority = Priority.HIGHEST


def generate_names(name_format='{name}-{serial:02d}', **kwargs):
    """Useful for generate names of an actor with a serial number."""
    serial = kwargs.pop('serial', None) or AtomicInt(1)
    while True:
        yield name_format.format(serial=serial.get_and_add(1), **kwargs)
