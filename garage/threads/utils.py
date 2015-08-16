__all__ = [
    'AtomicInt',
    'AtomicSet',
    'TaskQueue',
]

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
