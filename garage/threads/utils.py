__all__ = [
    'AtomicInt',
    'AtomicSet',
]

import threading


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
