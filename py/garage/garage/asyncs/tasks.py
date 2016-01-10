__all__ = [
    'TaskMonitor',
]

import asyncio
import logging


LOG = logging.getLogger(__name__)


class TaskMonitor:

    def __init__(self, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.tasks = set()

    def add(self, coro):
        task = self.loop.create_task(coro)
        task.add_done_callback(self._on_task_done)
        self.tasks.add(task)
        return task

    async def wait(self, *, timeout=None, return_when=asyncio.ALL_COMPLETED):
        if not self.tasks:
            return None
        done, pending = await asyncio.wait(
            self.tasks,
            loop=self.loop, timeout=timeout, return_when=return_when)
        self.tasks.clear()
        for task in done:
            task.result()
        return pending

    def _on_task_done(self, task):
        self.tasks.remove(task)
        try:
            task.result()
        except Exception:
            LOG.exception('error in task %r', task)
