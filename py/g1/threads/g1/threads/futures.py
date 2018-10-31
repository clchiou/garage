"""Futures.

This is a simpler implementation of future than the standard library.
It also, in my opinion, removes confusing parts of standard library's
future implementation.
"""

__all__ = [
    'Future',
    'Timeout',
    'wrap_thread_target',
]

import contextlib
import functools
import logging
import threading

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
