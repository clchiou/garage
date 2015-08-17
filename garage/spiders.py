"""A simple web spider implementation."""

__all__ = [
    'Spider',
    'Parser',
    'Web',
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


### Data model of the web spiders.


class Parser:
    """Application-specific business logics."""

    def parse(self, req, rep):
        """Parse response and return a document object."""
        raise NotImplementedError

    def on_request_error(self, req, error):
        """Called on HTTP request error.

           Return True for re-raising the exception.
        """
        return True

    def on_estimate(self, estimate, doc):
        """Feedback on how accurate the estimate was given the resulting
           document (this is optional).
        """


class Web:
    """A web is a collection of inter-connected documents."""

    def is_outside(self, uri, from_document=None):
        """True if the URI (from some document) is outside the boundary
           of this web.
        """
        return False  # A boundary-less web.


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


### The spider class.


class Spider:

    def __init__(self, *,
                 parser,
                 web,
                 num_spiders=1,
                 client=None):
        self.parser = parser
        self.web = web
        self.client = client or clients.Client()
        self.task_queue = utils.TaskQueue(queues.PriorityQueue())
        self.uris = utils.AtomicSet()
        self.identities = utils.AtomicSet()
        self.future = supervisors.start_supervisor(
            num_spiders,
            functools.partial(tasklets.start_tasklet, self.task_queue),
        ).get_future()

    def crawl(self, req, estimate=None):
        """Enqueue a request for later processing."""
        if isinstance(req, str):
            req = clients.Request(method='GET', uri=req)

        if self.web.is_outside(req.uri):
            LOG.debug('exclude URI to the outside: %s', req.uri)
            return

        if self.uris.check_and_add(req.uri):
            LOG.debug('exclude crawled URI: %s', req.uri)
            return

        try:
            LOG.debug('enqueue: %s %s', req.method, req.uri)
            self.task_queue.put(_Task(estimate, req, self.handle))
        except queues.Closed:
            LOG.error('task_queue is closed when adding %s', req.uri)

    def handle(self, req, estimate):
        LOG.info('request %s %s', req.method, req.uri)
        try:
            rep = self.client.send(req)
        except clients.HttpError as exc:
            LOG.exception('cannot request %s %s', req.method, req.uri)
            if self.parser.on_request_error(req, exc):
                raise
            return

        doc = self.parser.parse(req, rep)
        if self.identities.check_and_add(doc.identity):
            LOG.debug('exclude URIs from crawled doc: %s', doc.identity)
            return

        for req, estimate in doc.links:
            self.crawl(req, estimate)

        self.parser.on_estimate(estimate, doc)


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
