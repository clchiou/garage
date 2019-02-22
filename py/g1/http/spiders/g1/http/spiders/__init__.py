"""Spiders.

* At the moment the spider provides minimal support of crawling; it does
  not detect duplicated requests, etc.

* The spider returns a serial number for each HTTP request for later
  reference.

* Each HTTP request has priority.  This is less of a feature but more of
  a workaround: When crawling, to avoid request queue from growing too
  long, the spider would prioritize requests that will result in less
  new requests enqueued, and it relies on the controller to tell it
  about that.
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

from g1.asyncs.bases import locks
from g1.asyncs.bases import tasks
from g1.bases.assertions import ASSERT
from g1.http import clients

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


class Controller:
    """Control how a spider crawls.

    For any request, exactly one of the callbacks (``on_request_error``
    and ``on_response``) is called.
    """

    async def on_crawl_start(self, spider):
        """Callback at the start of ``Spider.crawl``."""

    async def on_request_error(self, spider, serial, request, exc):
        """Callback on HTTP request errors."""

    async def on_response(self, spider, serial, request, response):
        """Callback on HTTP responses."""

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
        max_num_tasks=0,
    ):

        self.controller = controller

        self.session = session or clients.Session()

        # For coordination between _spawn_handlers and _join_handlers.
        self._gate = locks.Gate()

        self._request_queue = []

        # Cap the maximum number of concurrent handler tasks.  Since
        # each handler task sends one HTTP request (more if it retries),
        # it does not make sense to have handler tasks much more than
        # executor threads, or else the executor's queue will have huge
        # backlog.
        self._max_num_tasks = ASSERT.greater(
            max_num_tasks or 8 * len(self.session.executor.stubs),
            0,
        )
        self._handler_tasks = tasks.CompletionQueue()

        self._to_join_tasks = []

    async def crawl(self):
        """Start crawling.

        A spider object can only crawl once.
        """

        ASSERT.false(self._handler_tasks.is_closed())

        async with contextlib.AsyncExitStack() as stack:

            stack.callback(self._cleanup_request_queue)

            await self.controller.on_crawl_start(self)
            stack.push_async_exit(
                lambda *args: self.controller.on_crawl_stop(self, *args)
            )
            if not self._request_queue:
                LOG.warning('empty request queue')

            # Ensure that when ``on_crawl_stop`` is called, all handlers
            # were completed.
            await stack.enter_async_context(self._handler_tasks)
            stack.push_async_callback(self._cleanup_tasks)

            # If this task gets cancelled, this async-for-loop is the
            # most likely place to raise ``TaskCancellation``.
            async for task in tasks.as_completed((
                tasks.spawn_onto_stack(self._spawn_handlers, stack),
                tasks.spawn_onto_stack(self._join_handlers, stack),
            )):
                # This task should never raise.
                task.get_result_nonblocking()

    async def _spawn_handlers(self):
        while ((self._request_queue or self._handler_tasks)
               and not self._handler_tasks.is_closed()):
            num_tasks = self._max_num_tasks - len(self._handler_tasks)
            while self._request_queue and num_tasks > 0:
                self._handler_tasks.spawn(
                    self._handle(heapq.heappop(self._request_queue))
                )
                num_tasks -= 1
            await self._gate.wait()
        # To unblock ``_join_handlers``.
        self._handler_tasks.close()

    async def _join_handlers(self):
        async for task in self._handler_tasks:
            self._gate.unblock()
            # Handler task should never raise, but you never know.
            task.get_result_nonblocking()

    async def _handle(self, item):

        try:
            LOG.info('request: %r', item.request)
            try:
                response = await self.session.send(item.request)
            except Exception as exc:
                LOG.exception('request error: %r', item.request)
                await self.controller.on_request_error(
                    self, item.serial, item.request, exc
                )
                return

            try:
                await self.controller.on_response(
                    self, item.serial, item.request, response
                )
            except Exception:
                LOG.exception('on_response error: %r', item.request)
                return

        finally:
            self._gate.unblock()

    async def _cleanup_tasks(self):
        to_join_tasks, self._to_join_tasks = self._to_join_tasks, []
        for task in to_join_tasks:
            await tasks.join_and_log_on_error(task)

    def _cleanup_request_queue(self):
        if self._request_queue:
            LOG.warning('drop %d requests', len(self._request_queue))
            self._request_queue.clear()

    #
    # Interface to controller.
    #

    def enqueue(self, request, priority):
        """Enqueue a request; return a serial number."""

        if not isinstance(request, clients.Request):
            request = clients.Request('GET', ASSERT.isinstance(request, str))

        item = RequestQueueItem(
            RequestQueueItem.next_serial(), request, priority
        )

        heapq.heappush(self._request_queue, item)
        self._gate.unblock()

        return item.serial

    def request_shutdown(self, graceful=True):
        """Request spider to shut down.

        If ``graceful`` is false, all running handler tasks are
        cancelled.
        """
        LOG.info('request shutdown: graceful=%r', graceful)
        to_join_tasks = self._handler_tasks.close(graceful)
        self._gate.unblock()
        for task in to_join_tasks:
            task.cancel()
        self._to_join_tasks.extend(to_join_tasks)


class RequestQueueItem:

    next_serial = itertools.count(1).__next__

    __slots__ = ('serial', 'request', 'priority')

    def __init__(self, serial, request, priority):
        self.serial = serial
        self.request = request
        self.priority = priority

    def __lt__(self, other):
        return self.priority < other.priority
