"""A simple web spider implementation."""

__all__ = [
    'Spider',
    'Parser',
    'Document',
]

import functools
import logging

from garage.functools import nondata_property
from garage.http import clients
from garage.threads import queues
from garage.threads import supervisors
from garage.threads import tasklets
from garage.threads import utils


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


class Parser:
    """Application-specific business logics."""

    def is_outside(self, uri):
        """True if the URI (from some document) is outside the boundary
           of this web.
        """
        return False  # A boundary-less web.

    def parse(self, request, response):
        """Parse response and return a document object."""
        raise NotImplementedError

    def on_request_error(self, request, error):
        """Called on HTTP request error.

           Return True for re-raising the exception.
        """
        return True

    def on_estimate(self, estimate, document):
        """Feedback on how accurate the estimate was given the resulting
           document (this is optional).
        """


class Document:
    """A document of a web."""

    identity = nondata_property(doc="""
    The unique identity of this document (multiple URIs may point to the
    same document).
    """)

    links = nondata_property(doc="""
    Return HTTP requests and an estimate numbers of further links from
    that document (estimates could be None).
    """)


class Spider:

    def __init__(self, *,
                 parser,
                 num_spiders=1,
                 client=None):
        self.parser = parser
        self.client = client or clients.Client()
        self.task_queue = utils.TaskQueue(queues.PriorityQueue())
        self.uris = utils.AtomicSet()
        self.identities = utils.AtomicSet()
        self.future = supervisors.start_supervisor(
            num_spiders,
            functools.partial(tasklets.start_tasklet, self.task_queue),
        ).get_future()

    def crawl(self, request, estimate=None):
        """Enqueue a request for later processing."""
        if isinstance(request, str):
            request = clients.Request(method='GET', uri=request)

        if self.parser.is_outside(request.uri):
            LOG.debug('exclude URI to the outside: %s', request.uri)
            return

        if self.uris.check_and_add(request.uri):
            LOG.debug('exclude crawled URI: %s', request.uri)
            return

        try:
            LOG.debug('enqueue %r', request)
            self.task_queue.put(_Task(estimate, request, self.handle))
        except queues.Closed:
            LOG.error('task_queue is closed when adding %s', request.uri)

    def handle(self, request, estimate):
        LOG.info('request %s %s', request.method, request.uri)
        try:
            response = self.client.send(request)
        except clients.HttpError as exc:
            LOG.exception('cannot request %s %s', request.method, request.uri)
            if self.parser.on_request_error(request, exc):
                raise
            return

        document = self.parser.parse(request, response)
        if self.identities.check_and_add(document.identity):
            LOG.debug('exclude URIs from crawled document: %s',
                      document.identity)
            return

        for req_from_doc, estimate in document.links:
            self.crawl(req_from_doc, estimate)

        self.parser.on_estimate(estimate, document)


class _Task(utils.Priority):

    def __init__(self, estimate, request, handle):
        if estimate is None:
            priority = utils.Priority.LOWEST
        else:
            priority = estimate
        super().__init__(priority)
        self.estimate = estimate
        self.request = request
        self.handle = handle

    def __str__(self):
        return '_Task(%r, %r, %r)' % (self.estimate, self.request, self.handle)

    __repr__ = __str__

    def __call__(self):
        self.handle(self.request, self.estimate)
