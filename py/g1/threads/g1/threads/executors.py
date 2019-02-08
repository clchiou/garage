__all__ = [
    'Executor',
]

import itertools
import logging
import os

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
        queue = futures.CompletionQueue(stubs)
        queue.close()
        for f in queue.as_completed(timeout):
            exc = f.get_exception()
            if exc:
                LOG.error('executor crash: %r', stubs[f], exc_info=exc)
        if queue:
            LOG.warning('not join %d executor', len(queue))
