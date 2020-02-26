"""Define a global task queue for background jobs."""

import logging

from startup import startup

import g1.asyncs.agents.parts
from g1.bases import labels
from g1.asyncs.bases import tasks
from g1.asyncs.bases import timers

LABELS = labels.make_labels(__name__, 'queue')


@startup
def make_queue(
    agent_queue: g1.asyncs.agents.parts.LABELS.agent_queue,
    shutdown_queue: g1.asyncs.agents.parts.LABELS.shutdown_queue,
) -> LABELS.queue:
    bg = BackgroundTasks()
    agent_queue.spawn(bg.supervise)
    shutdown_queue.put_nonblocking(bg.shutdown)
    return bg.queue


LOG = logging.getLogger(__name__)

NON_GRACE_PERIOD = 0.1  # Unit: seconds.


class BackgroundTasks:

    def __init__(self):
        self.queue = tasks.CompletionQueue()
        self._leftover = []

    async def supervise(self):
        # We assume you don't care to join background jobs on process
        # exit; so don't `async with self.queue`, which joins tasks by
        # default.
        async for task in self.queue:
            exc = task.get_exception_nonblocking()
            if exc:
                LOG.warning('background task error: %r', task, exc_info=exc)
            else:
                LOG.debug('background task exit: %r', task)
        # NOTE: In a non-graceful exit, we won't reach here (so tasks
        # won't be cancelled by us), but that's fine since it's a
        # non-graceful exit anyway.
        leftover, self._leftover = self._leftover, []
        await _cleanup(leftover)

    def shutdown(self):
        # Use extend because shutdown could be called multiple times.
        self._leftover.extend(self.queue.close(graceful=False))


async def _cleanup(leftover):
    if not leftover:
        return
    LOG.info('cancel %d background tasks on exit', len(leftover))
    for task in leftover:
        task.cancel()
    leftover = set(leftover)
    with timers.timeout_ignore(NON_GRACE_PERIOD):
        async for task in tasks.as_completed(leftover):
            leftover.remove(task)
            exc = task.get_exception_nonblocking()
            if exc and not isinstance(exc, tasks.Cancelled):
                LOG.warning('background task error: %r', task, exc_info=exc)
    if leftover:
        LOG.warning('%d background tasks are still running', len(leftover))
