__all__ = [
    'crash_on',
    'prepare_crash',
]

import concurrent.futures.thread
import contextlib
import logging


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


@contextlib.contextmanager
def crash_on(executor, exc_class):
    try:
        yield executor
    except exc_class:
        prepare_crash(executor)
        raise


def prepare_crash(executor):
    """Clear thread queues (since we are going to crash)."""
    LOG.critical('prepare to carsh for %r', executor)
    executor.shutdown(wait=False)
    # XXX: Hack for clearing internal queues of concurrent.futures.thread.
    executor._threads.clear()
    concurrent.futures.thread._threads_queues.clear()
