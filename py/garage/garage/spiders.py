"""A simple web spider implementation."""

__all__ = [
    'Document',
    'Spider',
    'Parser',
]

import functools
import logging
import typing

from garage.collections import NamedTuple
from garage.http import clients
from garage.threads import queues
from garage.threads import supervisors
from garage.threads import tasklets
from garage.threads import utils


LOG = logging.getLogger(__name__)


# Your parser may return a compatible class of this (duck typing).
class Document(NamedTuple):

    # The unique identity of this document (multiple URIs may point to
    # the same document).
    identity: object

    # Return HTTP requests and an estimate numbers of further links from
    # that document (estimates could be None).
    links: typing.Tuple[typing.Tuple[str, object], ...]


class Parser:
    """Application-specific business logics."""

    def is_outside(self, uri):
        """True if the URI is outside the boundary of this spider."""
        return False  # A boundary-less web.

    def parse(self, request, response):
        """Parse response and return a document object."""
        raise NotImplementedError

    def on_request_error(self, request, error):
        """Callback on HTTP request error.

        Return False to suppress exception.
        """
        return True

    def on_parse_error(self, request, response, error):
        """Callback on error during parse().

        Return False to suppress exception.
        """
        return True

    def on_document(self, document):
        """Callback to further process the document."""

    def on_document_error(self, request, document, error):
        """Callback on error during on_document().

        Return False to suppress exception.
        """
        return True

    def on_estimate(self, estimate, document):
        """Callback to assess accuracy of the estimations."""

    def on_estimate_error(self, request, estimate, document, error):
        """Callback on error during on_estimate().

        Return False to suppress exception.
        """
        return True


class Spider:

    def __init__(self, *,
                 parser,
                 num_spiders=1,
                 client=None):
        self._parser = parser
        self._client = client or clients.Client()
        self._task_queue = tasklets.TaskQueue(queues.PriorityQueue())
        # XXX: Use a cache for these two sets?
        self._uris = utils.AtomicSet()
        self._identities = utils.AtomicSet()

        self.num_spiders = num_spiders
        self.future = None

    def start(self):
        """Start crawling the web.

        We don't start crawling right after the spider is initialized
        due to a task queue's design limitation that you should not put
        new tasks into it after tasklets are started (the queue may have
        been closed already).  I'm not saying you can't, but you might
        encounter an queues.Closed error.
        """
        supervisor = supervisors.supervisor(
            self.num_spiders,
            functools.partial(tasklets.tasklet, self._task_queue),
        )
        # Use this future to wait for completion of the crawling
        self.future = supervisor._get_future()

    def stop(self, graceful=True):
        items = self._task_queue.close(graceful)
        LOG.info('stop spider; drop %d tasks', len(items))

    def crawl(self, request, estimate=None):
        """Enqueue a request for later processing."""
        if isinstance(request, str):
            request = clients.Request(method='GET', uri=request)

        if self._parser.is_outside(request.uri):
            LOG.debug('exclude URI to the outside: %s', request.uri)
            return

        if request.method == 'GET' and self._uris.check_and_add(request.uri):
            LOG.debug('exclude crawled URI: %s', request.uri)
            return

        try:
            LOG.debug('enqueue %r', request)
            self._task_queue.put(Task(self, request, estimate))
        except queues.Closed:
            LOG.error('task_queue is closed when adding %s', request.uri)

    # Called by Task.
    def process(self, request, estimate):
        LOG.debug('request %s %s', request.method, request.uri)
        try:
            response = self._client.send(request)
        except clients.HttpError as exc:
            LOG.warning('cannot request %s %s', request.method, request.uri)
            if self._parser.on_request_error(request, exc):
                raise
            return  # Cannot proceed; return now.

        try:
            document = self._parser.parse(request, response)
        except Exception as exc:
            LOG.exception('cannot parse %s %s', request.method, request.uri)
            if self._parser.on_parse_error(request, response, exc):
                raise
            return  # Cannot proceed; return now.

        if document is None:
            LOG.debug('cannot parse %s %s', request.method, request.uri)
            return

        if self._identities.check_and_add(document.identity):
            LOG.debug(
                'exclude URIs from crawled document: %s',
                document.identity,
            )
            return

        for req_from_doc, estimate in document.links:
            self.crawl(req_from_doc, estimate)

        try:
            self._parser.on_document(document)
        except Exception as exc:
            LOG.exception(
                'cannot handle document %s %s', request.method, request.uri)
            if self._parser.on_document_error(request, document, exc):
                raise

        try:
            self._parser.on_estimate(estimate, document)
        except Exception as exc:
            LOG.exception(
                'cannot estimate document %s %s', request.method, request.uri)
            if self._parser.on_estimate_error(
                    request, estimate, document, exc):
                raise


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
