__all__ = [
    'tasklet',
]

import logging

from garage.threads import actors
from garage.threads import queues


LOG = logging.getLogger(__name__)


@actors.OneShotActor.make
def tasklet(task_queue):
    """A tasklet is a long-running consumer of a task queue, and it dies
       immediately after the queue being closed.

       A tasklet will notify the task queue when tasks have been
       processed (and so you shouldn't have to do it yourself).

       A task is any callable object.
    """
    LOG.info('start')
    while True:
        try:
            task = task_queue.get()
        except queues.Closed:
            break
        try:
            task()
        finally:
            task_queue.notify_task_processed()
        del task
    LOG.info('exit')
