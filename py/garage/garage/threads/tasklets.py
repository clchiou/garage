__all__ = [
    'TaskQueue',
    'tasklet',
]

import logging

from garage import asserts
from garage.threads import actors
from garage.threads import queues


LOG = logging.getLogger(__name__)


class TaskQueue(queues.ForwardingQueue):
    """A task queue (vs executor) is for scenarios that the number of
    total tasks is not known in advance (and thus you do not know when
    you may close the queue).  This happens when a task may spawn more
    tasks depending on the task's outcome.

    We implement a simple strategy to determine when a task queue may
    safely close itself: a task queue tracks the number of tasks and
    running tasklets, and it closes itself when both are zero.  If no
    tasklet is running, no new tasks will be put into the queue.  If at
    the same time, there is no task in the queue, we should be safe to
    conclude that there will never be new tasks (unless you are still
    putting new tasks into the queue - which you shouldn't; see below).

    NOTE: The limitation of this simple strategy is that once you put
    the initial tasks into the task queue, you should not put any more
    tasks into the queue because the queue may have already been closed.
    If you do want to put tasks into the queue after tasklets start, you
    will have to implement your task queue.  (But this simple strategy
    should work for most scenarios.)

    You may use this auto-close feature to wait for the completion of
    all tasks.
    """

    def __init__(self, queue):
        super().__init__(queue)
        self.__num_running_tasklets = 0

    def get_task(self):
        asserts.greater_or_equal(self.__num_running_tasklets, 0)
        with self.lock:
            task = self.get()
            self.__num_running_tasklets += 1
            return task

    # idle = not running
    def notify_tasklet_idle(self):
        asserts.greater(self.__num_running_tasklets, 0)
        with self.lock:
            self.__num_running_tasklets -= 1
            asserts.greater_or_equal(self.__num_running_tasklets, 0)
            # We may close the queue when both conditions (no running
            # tasklets and no tasks) are met.
            if self.__num_running_tasklets == 0 and not self:
                self.close()


@actors.OneShotActor.from_func
def tasklet(task_queue):
    """A tasklet consumes task from a task queue, and it exits when the
    task queue is closed.

    A tasklet notifies the task queue when it has executed the task and
    becomes idle again.
    """
    LOG.info('start')
    while True:
        try:
            task = task_queue.get_task()
        except queues.Closed:
            break
        try:
            task()
        finally:
            task_queue.notify_tasklet_idle()
        del task
    LOG.info('exit')
