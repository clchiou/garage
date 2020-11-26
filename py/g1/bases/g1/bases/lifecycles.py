"""Helpers for tracking object life cycle."""

__all__ = [
    'add_to',
    'monitor_object_aliveness',
    'take_snapshot',
]

import collections
import threading
import weakref


class AliveObjectCounter:

    def __init__(self):
        self._counter = collections.Counter()
        self._lock = threading.Lock()

    def take_snapshot(self):
        with self._lock:
            return self._counter.copy()

    def monitor_object_aliveness(self, obj, key=None):
        # NOTE: We cannot monitor built-in objects because most(?) of
        # them do not support weak reference.
        if key is None:
            key = type(obj)
        weakref.finalize(obj, self.add_to, key, -1)
        self.add_to(key, 1)

    def add_to(self, key, count):
        with self._lock:
            self._counter[key] += count


_ALIVE_OBJECT_COUNTER = AliveObjectCounter()
take_snapshot = _ALIVE_OBJECT_COUNTER.take_snapshot
monitor_object_aliveness = _ALIVE_OBJECT_COUNTER.monitor_object_aliveness
add_to = _ALIVE_OBJECT_COUNTER.add_to
