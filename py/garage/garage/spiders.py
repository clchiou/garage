"""A simple web spider implementation."""

__all__ = [
    'Document',
    'Spider',
    'Parser',
]

import functools
import logging
from collections import namedtuple

from garage.http import clients
from garage.threads import queues
from garage.threads import supervisors
from garage.threads import tasklets
from garage.threads import utils


LOG = logging.getLogger(__name__)


# Your parser may return a compatible class of this (duck typing).
Document = namedtuple('Document', [

    # The unique identity of this document (multiple URIs may point to
    # the same document).
    'identity',

    # Return HTTP requests and an estimate numbers of further links from
    # that document (estimates could be None).
    'links',
])


class Parser:
    """Application-specific business logics."""

    def is_outside(self, uri):
        """True if the URI is outside the boundary of this spider."""
        return False  # A boundary-less web.

    def parse(self, request, response):
        """Parse response and return a document object."""
        raise NotImplementedError

    def on_request_error(self, request, error):
        """Called on HTTP request error.

           Return True for re-raising the exception.
        """
        return True

    def on_parse_error(self, request, response, error):
        """Called on error during parse().

           Return True for re-raising the exception.
        """
        return True

    def on_document(self, document):
        """Further processing of the document."""

    def on_estimate(self, estimate, document):
        """You may use this callback to get a feedback of how accurate
           the estimate was.
        """


class Spider:

    def __init__(self, *,
                 parser,
                 num_spiders=1,
                 client=None):
        self._parser = parser
        self._client = client or clients.Client()
        self._task_queue = utils.TaskQueue(queues.PriorityQueue())
        # XXX: Use a cache for these two sets?
        self._uris = utils.AtomicSet()
        self._identities = utils.AtomicSet()

        supervisor = supervisors.start_supervisor(
            num_spiders,
            functools.partial(tasklets.start_tasklet, self._task_queue),
        )
        # Use this future to wait for completion of the crawling.
        self.future = supervisor.get_future()

    def crawl(self, request, estimate=None):
        """Enqueue a request for later processing."""
        if isinstance(request, str):
            request = clients.Request(method='GET', uri=request)

        if self._parser.is_outside(request.uri):
            LOG.debug('exclude URI to the outside: %s', request.uri)
            return

        if self._uris.check_and_add(request.uri):
            LOG.debug('exclude crawled URI: %s', request.uri)
            return

        try:
            LOG.debug('enqueue %r', request)
            self._task_queue.put(Task(self, request, estimate))
        except queues.Closed:
            LOG.error('task_queue is closed when adding %s', request.uri)

    # Called by Task.
    def process(self, request, estimate):
        LOG.info('request %s %s', request.method, request.uri)
        try:
            response = self._client.send(request)
        except clients.HttpError as exc:
            LOG.exception('cannot request %s %s', request.method, request.uri)
            if self._parser.on_request_error(request, exc):
                raise
            return

        try:
            document = self._parser.parse(request, response)
        except Exception as exc:
            LOG.exception('cannot parse %s %s', request.method, request.uri)
            if self._parser.on_parse_error(request, response, exc):
                raise
            return

        if document is None:
            LOG.debug('cannot parse %s %s', request.method, request.uri)
            return

        if self._identities.check_and_add(document.identity):
            LOG.debug('exclude URIs from crawled document: %s',
                      document.identity)
            return

        for req_from_doc, estimate in document.links:
            self.crawl(req_from_doc, estimate)

        self._parser.on_document(document)

        self._parser.on_estimate(estimate, document)


class Task:

    def __init__(self, spider, request, estimate):
        if estimate is None:
            self.priority = utils.Priority.LOWEST
        else:
            self.priority = utils.Priority(estimate)
        self.spider = spider
        self.request = request
        self.estimate = estimate

    def __lt__(self, other):
        return self.priority < other.priority

    def __call__(self):
        self.spider.process(self.request, self.estimate)
