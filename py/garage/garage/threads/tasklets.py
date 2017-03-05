__all__ = [
    'start_tasklet',
]

import logging

from garage.threads import actors
from garage.threads import queues
from garage.threads import utils


LOG = logging.getLogger(__name__)


def start_tasklet(task_queue):
    return actors.build(tasklet,
                        name=next(start_tasklet.names),
                        set_pthread_name=True,
                        args=(task_queue,))


start_tasklet.names = utils.generate_names(name='tasklet')


@actors.OneShotActor
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
