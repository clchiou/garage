__all__ = [
    'Executor',
    'PriorityExecutor',
]

import itertools
import logging
import os
import weakref

from g1.bases.assertions import ASSERT
from g1.threads import actors
from g1.threads import futures
from g1.threads import queues

LOG = logging.getLogger(__name__)


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
        self.stubs = tuple(
            actors.Stub(
                name=name,
                actor=actors.function_caller,
                queue=self.queue,
                daemon=daemon,
            ) for name in names
        )

        # Add this ``finalize`` so that, when the application does not
        # shut down the executor and did not set daemon to true, the
        # actor threads (and then the main process) could still exit.
        weakref.finalize(self, _finalize_executor, self.queue)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        self.shutdown(graceful=not exc_type)

    def submit(self, func, *args, **kwargs):
        future = futures.Future()
        call = actors.MethodCall(
            method=func, args=args, kwargs=kwargs, future=future
        )
        self.queue.put(call)
        return future

    def shutdown(self, graceful=True, timeout=None):
        items = self.queue.close(graceful)
        if items:
            LOG.warning('drop %d tasks', len(items))
        if graceful:
            self._join(timeout)
        return items

    def _join(self, timeout):
        stubs = {stub.future: stub for stub in self.stubs}
        for f in futures.as_completed(stubs, timeout):
            stub = stubs.pop(f)
            exc = f.get_exception()
            if exc:
                LOG.error('executor crash: %r', stub, exc_info=exc)
        if stubs:
            LOG.warning('not join %d executor', len(stubs))


def _finalize_executor(queue):
    # If we end up here, it is likely that the remaining tasks in the
    # queue should not even be started (thus ``graceful=False``).
    num_items = len(queue.close(graceful=False))
    if num_items:
        LOG.warning('finalize: drop %d tasks', num_items)


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
