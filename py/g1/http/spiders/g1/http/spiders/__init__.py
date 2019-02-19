"""Spiders.

* This spider is designed for crawling one website; it is possible but
  probably not great for crawling the WWW.

* This spider is essentially a very primitive job dependency solver (it
  does not check cycles, etc.).  In the future we might improve it on
  this aspect, but for now this primitive solver seems to be enough.

* Each job has priority.  This is less of a feature but more of
  a workaround: When crawling, to avoid job queue size from growing out
  of control, the spider should prioritize nodes with less out-degrees,
  and it relies on the controller to tell it about that.

* Each job may have an HTTP request; the request is associated with a
  request ID (default to its URL).  The spider uses these IDs to avoid
  sending duplicated request.  On duplicated requests, the controller's
  ``on_response`` will **not** be called.
"""

__all__ = [
    'Controller',
    'Spider',
]

import collections
import contextlib
import heapq
import itertools
import logging

from g1.asyncs import kernels
from g1.bases.assertions import ASSERT
from g1.http import clients

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


class Controller:
    """Control how a spider crawls.

    For any job, exactly one of the callbacks (``on_request_not_sent``,
    ``on_request_error``, and ``on_response``) will be called.
    """

    async def on_crawl_start(self, spider):
        """Callback at the start of ``Spider.crawl``."""

    async def on_request_not_sent(self, spider, job_id, request):
        """Callback on duplicated requests."""

    async def on_request_error(self, spider, job_id, request, exc):
        """Callback on HTTP request errors."""

    async def on_response(self, spider, job_id, request, response):
        """Callback on HTTP responses.

        If a job does not have an HTTP request, the request and response
        objects are ``None``.
        """

    async def on_crawl_stop(self, spider, exc_type, exc_value, traceback):
        """Callback at the end of ``Spider.crawl``.

        The last three arguments are from the context manager (in case
        you are interested in handling errors of ``Spider.crawl``).
        """


class Spider:

    def __init__(
        self,
        controller,
        *,
        session=None,
        check_request_id=True,
        max_num_tasks=0,
    ):

        self.controller = controller

        self.session = session or clients.Session()

        if check_request_id:
            self._check_request_id = RequestIdChecker()
        else:
            self._check_request_id = dont_check_request_id

        # Map from job ID to jobs that depend on this job ID.
        self._job_graph = collections.defaultdict(collections.deque)
        self._completed_job_ids = set()

        # For coordination between _spawn_handlers and _join_handlers.
        self._gate = kernels.Gate()

        # Jobs that are ready for execution.
        self._job_queue = []

        # Cap the maximum number of concurrent handler tasks.  Since
        # each handler task sends one HTTP request (more if it retries),
        # it does not make sense to have handler tasks much more than
        # executor threads, or else the executor's queue will have huge
        # backlog.
        self._max_num_tasks = ASSERT.greater(
            max_num_tasks or 8 * len(self.session.executor.stubs),
            0,
        )
        self._handler_tasks = kernels.CompletionQueue()

        self._to_join_tasks = []

    async def crawl(self):
        """Start crawling.

        A spider object can only crawl once.
        """

        ASSERT.false(self._handler_tasks.is_closed())

        async with contextlib.AsyncExitStack() as stack:

            stack.callback(self._cleanup_jobs)

            await self.controller.on_crawl_start(self)
            stack.push_async_exit(
                lambda *args: self.controller.on_crawl_stop(self, *args)
            )
            if not self._job_queue:
                LOG.warning('no initial jobs after on_crawl_start')

            # Ensure that when ``on_crawl_stop`` is called, all handlers
            # were completed.
            await stack.enter_async_context(self._handler_tasks)
            stack.push_async_callback(self._cleanup_tasks)

            # If this task gets cancelled, this async-for-loop is the
            # most likely place to raise ``TaskCancellation``.
            async for task in kernels.as_completed((
                await stack.enter_async_context(
                    kernels.joining(kernels.spawn(self._spawn_handlers))
                ),
                await stack.enter_async_context(
                    kernels.joining(kernels.spawn(self._join_handlers))
                ),
            )):
                # This task should never raise.
                task.get_result_nonblocking()

    async def _spawn_handlers(self):
        while ((self._job_graph or self._job_queue or self._handler_tasks)
               and not self._handler_tasks.is_closed()):
            num_tasks = self._max_num_tasks - len(self._handler_tasks)
            while self._job_queue and num_tasks > 0:
                job = heapq.heappop(self._job_queue)
                self._handler_tasks.spawn(self._handle(job))
                num_tasks -= 1
            await self._gate.wait()
        # To unblock ``_join_handlers``.
        self._handler_tasks.close()

    async def _join_handlers(self):
        async for task in self._handler_tasks:
            self._gate.unblock()
            # Handler task should never raise, but you never know.
            task.get_result_nonblocking()

    async def _handle(self, job):

        try:
            if not job.request:
                # In this case, both request and response are ``None``.
                response = None

            elif self._check_request_id(job.request_id):
                LOG.debug(
                    'not send duplicated request: %r, %r',
                    job.request_id,
                    job.request,
                )
                try:
                    await self.controller.on_request_not_sent(
                        self, job.id, job.request
                    )
                except Exception:
                    LOG.exception('on_request_not_sent error: %r', job.request)
                # In this case, do not call ``on_response``.
                return

            else:
                LOG.info('request: %r', job.request)
                try:
                    response = await self.session.send(job.request)
                except Exception as exc:
                    LOG.exception('request error: %r', job.request)
                    await self.controller.on_request_error(
                        self, job.id, job.request, exc
                    )
                    return

            try:
                await self.controller.on_response(
                    self, job.id, job.request, response
                )
            except Exception:
                LOG.exception('on_response error: %r', job.request)
                return

        finally:
            # This job is completed (whether it errs out or not).  Let's
            # unblock jobs that are depending on this job.
            self._completed_job_ids.add(job.id)
            do_unblock = False
            for other_job in self._job_graph.pop(job.id, ()):
                other_job.dependencies.remove(job.id)
                if not other_job.dependencies:
                    heapq.heappush(self._job_queue, other_job)
                    do_unblock = True
            if do_unblock:
                self._gate.unblock()

    async def _cleanup_tasks(self):
        tasks, self._to_join_tasks = self._to_join_tasks, []
        for task in tasks:
            exc = await task.get_exception()
            if exc and not isinstance(exc, kernels.Cancelled):
                LOG.error('handler task error: %r', task, exc_info=exc)

    def _cleanup_jobs(self):
        if self._job_graph or self._job_queue:
            LOG.warning(
                'drop %d jobs',
                len(self._job_queue) + len({
                    job.id
                    for jobs in self._job_graph.values()
                    for job in jobs
                }),
            )
            self._job_graph.clear()
            self._job_queue.clear()

    #
    # Interface to controller.
    #

    def enqueue(
        self,
        *,
        priority,
        request_id=None,
        request=None,
        dependencies=(),
    ):
        """Add a job to the spider; return job id."""

        if request:
            if not isinstance(request, clients.Request):
                request = clients.Request(
                    'GET', ASSERT.isinstance_(request, str)
                )
            if request_id is None:
                request_id = request.url
        else:
            ASSERT.none(request_id)

        job = Job(
            id=Job.next_id(),
            priority=priority,
            request_id=request_id,
            request=request,
            dependencies=set(dependencies),
        )
        # Remove dependencies to completed jobs.
        job.dependencies.difference_update(self._completed_job_ids)

        if job.dependencies:
            for dep_job_id in job.dependencies:
                self._job_graph[dep_job_id].append(job)
        else:
            heapq.heappush(self._job_queue, job)
            self._gate.unblock()

        return job.id

    def request_shutdown(self, graceful=True):
        """Request spider to shut down.

        If ``graceful`` is false, all running handler tasks are
        cancelled.
        """
        LOG.info('request shutdown: graceful=%r', graceful)
        tasks = self._handler_tasks.close(graceful)
        self._gate.unblock()
        for task in tasks:
            task.cancel()
        self._to_join_tasks.extend(tasks)


def dont_check_request_id(_):
    return False


class RequestIdChecker:

    def __init__(self):
        self._request_ids = set()

    def __call__(self, request_id):
        have_seen = request_id in self._request_ids
        self._request_ids.add(request_id)
        return have_seen


class Job:

    next_id = itertools.count(1).__next__

    __slots__ = (
        'id',
        'priority',
        'request_id',
        'request',
        'dependencies',
    )

    def __init__(
        self,
        *,
        id,  # pylint: disable=redefined-builtin
        priority,
        request_id,
        request,
        dependencies,
    ):
        self.id = id
        self.priority = priority
        self.request_id = request_id
        self.request = request
        self.dependencies = dependencies

    def __lt__(self, other):
        return self.priority < other.priority
