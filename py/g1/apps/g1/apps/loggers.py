"""Configure loggers.

NOTE: This module has import-time side effect that it may configure
early logging (for debugging).
"""

__all__ = [
    'TRACE',
]

import logging
import os
import threading


def add_arguments(parser):
    parser.add_argument(
        '-v',
        '--verbose',
        action='count',
        default=0,
        help='increase log level',
    )


def configure_logging(args):
    _configure_logging(logging.INFO, args.verbose)


def _configure_logging(level, verbose):
    fmt = '%(asctime)s %(threadName)s %(levelname)s %(name)s: %(message)s'
    levels = (logging.WARNING, logging.INFO, logging.DEBUG, TRACE)
    index = min(levels.index(level) + verbose, len(levels) - 1)
    logging.basicConfig(level=levels[index], format=fmt)


# Add a new, finer logging level.
TRACE = logging.DEBUG - 1
logging.addLevelName(TRACE, 'TRACE')

# For prettier logging messages.
threading.main_thread().name = 'main'

# Check if debug logging is enabled.
if os.environ.get('DEBUG', '').lower() not in ('', '0', 'false'):
    _configure_logging(logging.DEBUG, 0)
    logging.getLogger(__name__).debug('start at DEBUG level')
