__all__ = [
    'Executor',
]

import itertools
import logging
import os

from g1.bases import timers
from g1.bases.assertions import ASSERT
from g1.threads import actors
from g1.threads import futures
from g1.threads import queues

LOG = logging.getLogger(__name__)


class Executor:

    _COUNTER = itertools.count(1).__next__

    def __init__(
        self,
        max_executors=None,
        *,
        name_prefix=None,
        daemon=None,
    ):

        if max_executors is None:
            # Use this because Executor is often used to parallelize I/O
            # instead of computationally-heavy tasks.
            max_executors = (os.cpu_count() or 1) * 8
        ASSERT.greater(max_executors, 0)

        if name_prefix is None:
            names = (
                'executor-%02d' % self._COUNTER()
                for _ in range(max_executors)
            )
        else:
            names = (
                '%s-%02d' % (name_prefix, i) for i in range(max_executors)
            )

        self.queue = queues.Queue()
        self.stubs = tuple(
            actors.Stub(
                name=name,
                actor=actors.function_caller,
                queue=self.queue,
                daemon=daemon,
            ) for name in names
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.shutdown()

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
        timer = timers.make(timeout)
        for stub in self.stubs:
            exc = stub.future.get_exception(timer.get_timeout())
            if exc:
                LOG.error('actor crash: %r', stub, exc_info=exc)
        return items