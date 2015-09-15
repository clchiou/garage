__all__ = [
    'init',
]

import logging
import threading

from startup import startup

from garage.functools import run_once

import garage
from garage.startups import ARGS, PARSE, PARSER


VERBOSE = __name__ + ':verbose'


LOG_FORMAT = '%(asctime)s %(threadName)s %(levelname)s %(name)s: %(message)s'


def add_arguments(parser: PARSER, verbose: VERBOSE) -> PARSE:
    group = parser.add_argument_group(garage.__name__)
    group.add_argument(
        '-v', '--verbose', action='count', default=verbose,
        help='verbose output')


def configure(args: ARGS):
    if args.verbose == 0:
        level = logging.WARNING
    elif args.verbose == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG
    logging.basicConfig(level=level, format=LOG_FORMAT)
    threading.current_thread().name = garage.__name__ + '#main'


@run_once
def init(verbose=0):
    # XXX: Hack for manipulating startup order.
    add_arguments.__module__ = garage.__name__
    configure.__module__ = garage.__name__

    startup.set(VERBOSE, verbose)
    startup(add_arguments)
    startup(configure)
