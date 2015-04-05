__all__ = [
    'prepare_crash'
]

import concurrent.futures.thread
import logging


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


def prepare_crash(executor):
    """Clear thread queues (since we are going to crash)."""
    LOG.critical('prepare to carsh for %r', executor)
    executor.shutdown(wait=False)
    # XXX: Hack for clearing internal queues of concurrent.futures.thread.
    executor._threads.clear()
    concurrent.futures.thread._threads_queues.clear()
