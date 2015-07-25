"""Executors with a shared worker pool."""

__all__ = [
    'Executor',
    'WorkerPool',
]

import collections
import concurrent.futures
import logging
import queue
import threading


from garage import actors


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


Work = collections.namedtuple('Work', 'future func args kwargs')


class _Worker:

    @actors.method
    def work_on(self, work_queue):
        while True:
            work = work_queue.get()
            if work is None:  # This is a "kick".
                work_queue.put(None)
                break

            if not work.future.set_running_or_notify_cancel():
                del work
                continue

            try:
                result = work.func(*work.args, **work.kwargs)
            except BaseException as exc:
                work.future.set_exception(exc)
            else:
                work.future.set_result(result)
            del work


class Worker(actors.Stub, actor=_Worker):
    pass


class WorkerPool:

    def __init__(self):
        self._lock = threading.Lock()
        self._pool = collections.deque()

    def __len__(self):
        with self._lock:
            return len(self._pool)

    def __iter__(self):
        # Make a copy and then iterate on the copy.
        with self._lock:
            workers = list(self._pool)
        return iter(workers)

    def hire(self):
        """Called by executor to acquire more workers."""
        with self._lock:
            if not self._pool:
                return Worker()
            return self._pool.popleft()

    def return_to_pool(self, workers):
        """Called by executor to return workers to the pool."""
        with self._lock:
            for worker in workers:
                if worker.is_dead():
                    LOG.warn('worker is dead: %r', worker)
                else:
                    self._pool.append(worker)


class Executor(concurrent.futures.Executor):

    def __init__(self, worker_pool, max_workers):
        self._max_workers = max_workers
        self._worker_pool = worker_pool
        self._workers = []
        self._worker_waits = []
        # An unbounded queue will make things whole lot easier.
        self._work_queue = queue.Queue()
        self._shutdown_lock = threading.Lock()
        self._shutdown = False

    def submit(self, func, *args, **kwargs):
        with self._shutdown_lock:
            if self._shutdown:
                raise RuntimeError('executor has been shut down')

            future = concurrent.futures.Future()
            self._work_queue.put(Work(future, func, args, kwargs))

            # Hire more workers if we are still under budget.
            if len(self._workers) < self._max_workers:
                worker = self._worker_pool.hire()
                self._workers.append(worker)
                self._worker_waits.append(worker.work_on(self._work_queue))

            return future

    def shutdown(self, wait=True, graceful=True):
        """Shutdown the executor.

           If wait is True, shutdown() will blocks until all worker
           threads finish their jobs, but which jobs will be finished
           depends on graceful.

           If graceful is True, all the submitted jobs will be executed.
           Otherwise, the work queue will be drained (the worker threads
           will exit after they finish their current job at hand).

           NOTE: If you call shutdown multiple times, only the first
           call will be effective.
        """
        with self._shutdown_lock:
            if self._shutdown:
                return
            self._shutdown = True

        if not wait or not graceful:
            # Drain the work queue.
            while True:
                try:
                    work = self._work_queue.get_nowait()
                except queue.Empty:
                    break
                work.future.cancel()

        # "Kick" to stop the workers.
        self._work_queue.put(None)

        if wait:
            concurrent.futures.wait(self._worker_waits)
            self._worker_pool.return_to_pool(self._workers)
        else:
            # If we don't wait on them, we kill them.  Otherwise we
            # would return workers to the pool that are might still
            # working on our jobs (which others may not hire and use
            # immediately).
            for worker in self._workers:
                worker.kill(graceful=False)
