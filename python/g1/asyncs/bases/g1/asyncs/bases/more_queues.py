"""Queue utilities."""

__all__ = [
    'multiplex',
    'select',
]

import collections

from . import queues
from . import tasks


# Implement select by multiplex rather than the other way around to
# ensure that no input item is lost.
async def select(input_queues):
    """Select from input queues."""
    output_queue = queues.Queue()
    async with tasks.joining(
        tasks.spawn(multiplex(input_queues, output_queue)),
        always_cancel=True,
    ):
        while True:
            try:
                yield await output_queue.get()
            except queues.Closed:
                break


async def multiplex(input_queues, output_queue, *, close_output=True):
    """Multiplex from input queues in a round-robin order.

    It only reads an input queue when it can write to the output queue
    without blocking.  This ensures that no input item is lost when the
    task calling this function gets cancelled or output queue is closed.
    """
    try:
        async with tasks.CompletionQueue(always_cancel=True) as task_queue:
            await _multiplex(input_queues, output_queue, task_queue)
    finally:
        if close_output:
            output_queue.close()


async def _multiplex(input_queues, output_queue, task_queue):

    def move_first_to_gettable_tasks():
        """Move the first input queue to the gettable_tasks table."""
        input_queue = ready_queues.popleft()
        gettable_tasks[task_queue.spawn(input_queue.gettable())] = input_queue

    gettable_tasks = {
        task_queue.spawn(input_queue.gettable()): input_queue
        for input_queue in input_queues
    }
    ready_queues = collections.deque()
    while gettable_tasks:
        await output_queue.puttable()
        if output_queue.is_closed():
            break
        for gettable_task in await _all_completed(task_queue):
            gettable_task.get_result_nonblocking()
            ready_queues.append(gettable_tasks.pop(gettable_task))
        # Do NOT block after this point to avoid input item loss.  Also,
        # the output queue could be closed or full while we were waiting
        # for the input queues; so let us check it again.
        if output_queue.is_closed():
            break
        while ready_queues and not output_queue.is_full():
            try:
                item = ready_queues[0].get_nonblocking()
            except queues.Closed:
                ready_queues.popleft()
                continue
            except queues.Empty:
                move_first_to_gettable_tasks()
                continue
            output_queue.put_nonblocking(item)
            ready_queues.rotate(-1)
        # Move all remaining input queues back to gettable_tasks table
        # because output_queue is full.
        while ready_queues:
            move_first_to_gettable_tasks()


async def _all_completed(task_queue):
    """Return as many completed tasks as possible."""
    completed = [await task_queue.get()]
    while True:
        try:
            completed.append(task_queue.get_nonblocking())
        except (tasks.Closed, tasks.Empty):
            break
    return completed
