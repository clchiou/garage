__all__ = [
    'AtomicInt',
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
