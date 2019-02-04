"""Futures.

This is a simpler implementation of future than the standard library.
It also, in my opinion, removes confusing parts of standard library's
future implementation.
"""

__all__ = [
    'CompletionQueue',
    'Future',
    'Timeout',
    'wrap_thread_target',
]

import contextlib
import functools
import logging
import threading

from g1.bases import timers
from g1.bases.collections import Multiset
from g1.threads import queues

LOG = logging.getLogger(__name__)


class Timeout(Exception):
    pass


class Future:
    """Future object.

    The interface is divided into consumer-side and producer-side.
    Generally you make a ``Future`` object and pass it to both consumer
    and producer.

    On the producer side, you usually do:
    >>> with future.catching_exception(reraise=False):
    ...     future.set_result(42)

    Then on the consumer side, you get the result:
    >>> future.get_result()
    42
    """

    def __init__(self):
        self._condition = threading.Condition()
        self._completed = False
        self._result = None
        self._exception = None
        self._callbacks = []

    def __repr__(self):
        return '<%s at %#x: %s, %r, %r>' % (
            self.__class__.__qualname__,
            id(self),
            'completed' if self._completed else 'uncompleted',
            self._result,
            self._exception,
        )

    #
    # Consumer-side interface.
    #

    def is_completed(self):
        return self._completed

    def get_result(self, timeout=None):
        with self._condition:
            self._wait_for_completion(timeout)
            if self._exception:
                raise self._exception  # pylint: disable=raising-bad-type
            else:
                return self._result

    def get_exception(self, timeout=None):
        with self._condition:
            self._wait_for_completion(timeout)
            return self._exception

    def _wait_for_completion(self, timeout):
        if not self._completed:
            self._condition.wait(timeout)
            if not self._completed:
                raise Timeout

    def add_callback(self, callback):
        """Add a callback that is called on completion.

        There are a few caveats of ``add_callback``:

        * If a callback is added when the future has completed, the
          callback is executed on the caller thread; otherwise it is
          executed on the producer thread.

        * Exceptions raised from the callbacks are logged and then
          swallowed.

        And these caveats are the reason that you normally should not
        use ``add_callback``.
        """
        with self._condition:
            if not self._completed:
                self._callbacks.append(callback)
                return
        self._call_callback(callback)

    def _call_callback(self, callback):
        try:
            callback(self)
        except Exception:
            LOG.exception('callback err: %r, %r', self, callback)

    #
    # Producer-side interface.
    #

    @contextlib.contextmanager
    def catching_exception(self, *, reraise):
        """Catch exception automatically.

        NOTE: It catches ``BaseException``, not the usual ``Exception``.
        As a result, when the producer thread raises ``SystemExit``, it
        is caught and re-raised in the consumer thread; thus, even if
        the producer thread is not the main thread, it may still call
        ``sys.exit``, and the ``SystemExit`` might reach the main thread
        through the future object.
        """
        try:
            yield self
        except BaseException as exc:
            self.set_exception(exc)
            if reraise:
                raise

    def set_result(self, result):
        """Set future's result and complete the future.

        Once the future completes, further calling ``set_result`` or
        ``set_exception`` will be ignored.
        """
        self._set_result_or_exception(result, None)

    def set_exception(self, exception):
        """Set future's result with an exception.

        Otherwise this is the same as ``set_result``.
        """
        self._set_result_or_exception(None, exception)

    def _set_result_or_exception(self, result, exception):
        with self._condition:
            if self._completed:
                if exception:
                    LOG.error('ignore exception: %r', self, exc_info=exception)
                else:
                    LOG.error('ignore result: %r, %r', self, result)
                return
            self._result = result
            self._exception = exception
            self._completed = True
            callbacks, self._callbacks = self._callbacks, None
            self._condition.notify_all()
        for callback in callbacks:
            self._call_callback(callback)


class CompletionQueue:
    """Closable queue for waiting future completion.

    NOTE: Unlike other "regular" queues, since ``CompletionQueue`` only
    return completed futures, sometimes even when queue is not empty,
    ``get`` might not return anything if no future is completed yet.
    """

    def __init__(self, iterable=()):

        self._lock = threading.Lock()
        self._uncompleted = Multiset(iterable)
        self._completed = queues.Queue()
        self._closed = False

        # Since callbacks may acquire this again, use ``RLock`` instead
        # of regular lock.
        self._on_completion_callbacks_lock = threading.RLock()
        self._on_completion_callbacks = set()

        # Make a copy so that we may modify ``self._uncompleted`` while
        # iterating over its items.
        for f in tuple(self._uncompleted):
            f.add_callback(self._on_completion)

    def __repr__(self):
        with self._lock:
            num_uncompleted = len(self._uncompleted)
            num_completed = len(self._completed)
        return '<%s at %#x: %s, uncompleted=%d, completed=%d>' % (
            self.__class__.__qualname__,
            id(self),
            'closed' if self._closed else 'open',
            num_uncompleted,
            num_completed,
        )

    def __bool__(self):
        with self._lock:
            return bool(self._uncompleted) or bool(self._completed)

    def __len__(self):
        with self._lock:
            return len(self._uncompleted) + len(self._completed)

    def is_closed(self):
        with self._lock:
            return self._closed

    def close(self, graceful=True):
        with self._lock:
            if self._closed:
                return []
            if graceful:
                items = []
            else:
                items = self._completed.close(False)
                items.extend(self._uncompleted)
                self._uncompleted = ()
            self._closed = True
            return items

    def get(self, timeout=None):
        """Return a completed future."""
        with self._lock:
            if self._closed and not self._uncompleted and not self._completed:
                raise queues.Closed
        return self._completed.get(timeout)

    def put(self, future):
        with self._lock:
            if self._closed:
                raise queues.Closed
            self._uncompleted.add(future)
        future.add_callback(self._on_completion)

    def as_completed(self, timeout=None):
        """Iterate over completed futures."""
        if timeout is None or timeout <= 0:
            yield from self._as_completed_not_timed(timeout)
        else:
            yield from self._as_completed_timed(timeout)

    def _as_completed_not_timed(self, timeout):
        while True:
            try:
                yield self.get(timeout)
            except (queues.Empty, queues.Closed):
                break

    def _as_completed_timed(self, timeout):
        timer = timers.make(timeout)
        while True:
            timer.start()
            try:
                future = self.get(timer.get_timeout())
            except (queues.Empty, queues.Closed):
                break
            timer.stop()
            yield future

    def add_on_completion_callback(self, callback):
        """Add on-completion callback.

        These callbacks are fired when a ``Future`` object is moved from
        uncompleted queue to completed queue.
        """
        with self._on_completion_callbacks_lock:
            self._on_completion_callbacks.add(callback)

    def remove_on_completion_callback(self, callback):
        with self._on_completion_callbacks_lock:
            self._on_completion_callbacks.remove(callback)

    def _on_completion(self, future):
        """Move future from uncompleted set to completed queue."""
        with self._lock:
            if self._completed.is_closed():
                return  # This queue has been closed non-gracefully.
            # Since ``self._uncompleted`` is a ``Multiset``, ``remove``
            # should not raise ``KeyError``.
            self._uncompleted.remove(future)
            self._completed.put(future)
        with self._on_completion_callbacks_lock:
            for callback in self._on_completion_callbacks:
                callback(future)


def wrap_thread_target(target, *, reraise=True):
    """Wrap a thread's target function with a future object.

    With this, you may call ``sys.exit`` inside a thread, and re-raises
    the ``SystemExit`` in the main thread through the future object.

    Examples:
    >>> f = Future()
    >>> t = threading.Thread(target=wrap_thread_target(sys.exit), args=(f, 1))
    >>> t.start()
    >>> t.join()
    >>> f.get_exception()
    SystemExit(1)
    """

    @functools.wraps(target)
    def wrapper(future, *args, **kwargs):
        with future.catching_exception(reraise=reraise):
            future.set_result(target(*args, **kwargs))

    return wrapper