__all__ = [
    'start_tasklet',
]

import logging

from garage.threads import actors
from garage.threads import queues
from garage.threads import utils


LOG = logging.getLogger(__name__)


def start_tasklet(task_queue):
    stub = actors.build(Tasklet,
                        name=next(start_tasklet.names),
                        args=(task_queue,))
    # Make sure that a tasklet does not accept any new messages, and
    # dies immediately after start() returns.
    stub.start()
    stub.kill()
    return stub


start_tasklet.names = utils.generate_names(name='tasklet')


class _Tasklet:

    def __init__(self, task_queue):
        self.task_queue = task_queue

    @actors.method
    def start(self):
        LOG.info('start')
        while True:
            try:
                task = self.task_queue.get()
            except queues.Closed:
                break
            try:
                task()
            finally:
                self.task_queue.notify_task_processed()
            del task
        LOG.info('exit')
        raise actors.Exit


class Tasklet(actors.Stub, actor=_Tasklet):
    """A tasklet is a long-running consumer of a task queue, and it dies
       immediately after the queue being closed.

       A tasklet will notify the task queue when tasks have been
       processed (and so you shouldn't have to do it yourself).

       A task is any callable object.
    """
