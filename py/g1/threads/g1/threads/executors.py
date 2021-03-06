__all__ = [
    'Executor',
    'PriorityExecutor',
]

import itertools
import logging
import os
import sys

from g1.bases.assertions import ASSERT

from . import actors
from . import futures
from . import queues

LOG = logging.getLogger(__name__)

# Python 3.4 implements PEP 442 for safe ``__del__``.
ASSERT.greater_or_equal(sys.version_info, (3, 4))


class Executor:

    _COUNTER = itertools.count(1).__next__

    def __init__(
        self,
        max_executors=0,
        *,
        queue=None,
        name_prefix='',
        daemon=None,
    ):
        # In case ``__init__`` raises.
        self.queue = None
        if max_executors <= 0:
            # Use this because Executor is often used to parallelize I/O
            # instead of computationally-heavy tasks.
            max_executors = max(os.cpu_count(), 1) * 8
        if not name_prefix:
            names = (
                'executor-%02d' % self._COUNTER()
                for _ in range(max_executors)
            )
        else:
            names = (
                '%s-%02d' % (name_prefix, i) for i in range(max_executors)
            )
        self.queue = queue if queue is not None else queues.Queue()
        self.daemon = daemon
        self.stubs = tuple(
            actors.Stub(
                name=name,
                actor=actors.function_caller,
                queue=self.queue,
                daemon=self.daemon,
            ) for name in names
        )

    def __del__(self):
        # You have to check whether ``__init__`` raises.
        if self.queue is None:
            return
        num_items = len(self.queue.close(graceful=False))
        if num_items:
            LOG.warning('finalize: drop %d tasks', num_items)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        # Or should I use the actual daemon property that actor thread
        # has?  (It could be inherited from the thread that creates this
        # executor.)
        graceful = not exc_type and not self.daemon
        self.shutdown(graceful)
        try:
            self.join(None if graceful else actors.NON_GRACE_PERIOD)
        except futures.Timeout:
            pass

    def submit(self, func, *args, **kwargs):
        future = futures.Future()
        call = actors.MethodCall(
            method=func, args=args, kwargs=kwargs, future=future
        )
        self.queue.put(call)
        return future

    def shutdown(self, graceful=True):
        items = self.queue.close(graceful)
        if items:
            LOG.warning('drop %d tasks', len(items))
        return items

    def join(self, timeout=None):
        stubs = {stub.future: stub for stub in self.stubs}
        for f in futures.as_completed(stubs, timeout):
            stub = stubs.pop(f)
            exc = f.get_exception()
            if exc:
                LOG.error('executor crash: %r', stub, exc_info=exc)
        if stubs:
            LOG.warning('not join %d executors', len(stubs))
            raise futures.Timeout


class PriorityExecutor(Executor):
    """PriorityExecutor.

    This class is a sub-class of ``Executor`` sorely for inheriting its
    implementation, not its interface.  You should not treat this as a
    sub-type of ``Executor`` (thus Liskov Substitution Principle is not
    always applied to this class).  However, most of the time this class
    should be compatible with ``Executor``.
    """

    def __init__(self, *args, **kwargs):
        queue = kwargs.get('queue')
        default_priority = kwargs.pop('default_priority', None)
        ASSERT.xor(queue is None, default_priority is None)
        if queue is None:
            kwargs['queue'] = ExecutorPriorityQueue(default_priority)
        super().__init__(*args, **kwargs)

    def submit_with_priority(self, priority, func, *args, **kwargs):
        future = futures.Future()
        call = actors.MethodCall(
            method=func, args=args, kwargs=kwargs, future=future
        )
        self.queue.put_with_priority(priority, call)
        return future


class ExecutorPriorityQueue:
    """Priority queue specifically for ``PriorityExecutor``.

    This provides a queue-like interface that is somewhat compatible
    with the base ``Executor`` and its actors.
    """

    class Item:

        __slots__ = ('priority', 'item')

        def __init__(self, priority, item):
            self.priority = priority
            self.item = item

        def __lt__(self, other):
            return self.priority < other.priority

    def __init__(self, default_priority, queue=None):
        self._default_priority = default_priority
        self._queue = queue if queue is not None else queues.PriorityQueue()

    def close(self, graceful=True):
        return self._queue.close(graceful=graceful)

    def get(self, timeout=None):
        return self._queue.get(timeout=timeout).item

    def put(self, item, timeout=None):
        return self.put_with_priority(
            self._default_priority, item, timeout=timeout
        )

    def put_with_priority(self, priority, item, timeout=None):
        return self._queue.put(self.Item(priority, item), timeout=timeout)
