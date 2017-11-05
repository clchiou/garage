__all__ = [
    'AtomicInt',
    'AtomicSet',
    'Priority',
    'generate_names',
    'make_get_thread_local',
    'set_pthread_name',
]

import collections
import functools
import logging
import threading

from garage import asserts


LOG = logging.getLogger(__name__)


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


@functools.total_ordering
class Priority:
    """A wrapper class that supports lowest/highest priority sentinels,
       which should be handy when used with Python's heap.

       This is an immutable value class.

       NOTE: Python's heap[0] is the smallest item; so we will have the
       highest priority be the smallest.
    """

    def __init__(self, priority):
        asserts.type_of(priority, collections.Hashable)
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


def generate_names(*, name_format='{name}-{serial:02d}', **kwargs):
    """Useful for generate names of an actor with a serial number."""
    serial = kwargs.pop('serial', None) or AtomicInt(1)
    while True:
        yield name_format.format(serial=serial.get_and_add(1), **kwargs)


def make_get_thread_local(name, make):
    def get_thread_local():
        local = make_get_thread_local.local
        if not hasattr(local, name):
            setattr(local, name, make())
        return getattr(local, name)
    return get_thread_local


# Share thread local object globally
make_get_thread_local.local = threading.local()


# NOTE: This function is a hack; don't expect it to always work.
def set_pthread_name(thread, name):
    if not thread.ident:
        import warnings
        warnings.warn('no thread.ident for %r' % name)
        return
    name = name.encode('utf-8')
    if len(name) > 15:
        import warnings
        warnings.warn('pthread name longer than 16 char: %r' % name)
        return
    if not hasattr(set_pthread_name, 'pthread_setname_np'):
        import ctypes
        import ctypes.util
        try:
            pthread = ctypes.CDLL(ctypes.util.find_library('pthread'))
        except FileNotFoundError:
            LOG.warning('cannot load lib pthread', exc_info=True)
            pthread_setname_np = lambda *_: -1
        else:
            pthread_setname_np = pthread.pthread_setname_np
            # XXX: Evil: Use long for pthread_t, which is not quite true.
            pthread_setname_np.argtypes = [ctypes.c_long, ctypes.c_char_p]
            pthread_setname_np.restype = ctypes.c_int
        set_pthread_name.pthread_setname_np = pthread_setname_np
    # XXX: Evil: Use thread.ident as a shortcut of pthread_self().
    err = set_pthread_name.pthread_setname_np(thread.ident, name)
    if err:
        LOG.warning('cannot set pthread name (err=%d)', err)
