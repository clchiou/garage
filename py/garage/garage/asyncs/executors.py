__all__ = [
    'WorkerPoolAdapter',
    'ExecutorAdapter',
]

from asyncio.futures import wrap_future


class WorkerPoolAdapter:

    def __init__(self, worker_pool, *, loop=None):
        self.worker_pool = worker_pool
        self.loop = loop
        self._executor = self.worker_pool.make_executor(max_workers=1)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.shutdown()

    def make_executor(self, max_workers):
        executor = self.worker_pool.make_executor(max_workers)
        return ExecutorAdapter(executor, self._executor, loop=self.loop)

    # NOTE: This is blocking.
    def shutdown(self, wait=True):
        self._executor.shutdown(wait=wait)


class ExecutorAdapter:

    def __init__(self, executor, parent, *, loop=None):
        self.executor = executor
        self.parent = parent
        self.loop = loop

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.shutdown()

    def submit(self, func, *args, **kwargs):
        future = self.executor.submit(func, *args, **kwargs)
        return wrap_future(future, loop=self.loop)

    async def shutdown(self, wait=True):
        future = self.parent.submit(self.executor.shutdown, wait=wait)
        if wait:
            await wrap_future(future, loop=self.loop)
