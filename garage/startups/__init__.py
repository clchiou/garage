"""Initialize modules with startup.

The basic startup dependency graph is:

  PARSER ---> PARSE --+--> ARGS
                      |
              ARGV ---+
"""

__all__ = [
    'ARGS',
    'ARGV',
    'PARSE',
    'PARSER',
    'init',
    'init_logging',
]

import logging
import threading

from startup import startup

import garage
from garage.functools import run_once


ARGS = 'args'
ARGV = 'argv'
PARSE = 'parse'
PARSER = 'parser'


LOG_FORMAT = '%(asctime)s %(threadName)s %(levelname)s %(name)s: %(message)s'


def add_arguments(parser: PARSER) -> PARSE:
    group = parser.add_argument_group(garage.__name__)
    group.add_argument(
        '-v', '--verbose', action='count', default=0,
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


def parse_argv(parser: PARSER, argv: ARGV, _: PARSE) -> ARGS:
    return parser.parse_args(argv[1:])


@run_once
def init():
    startup(parse_argv)


@run_once
def init_logging():
    init()
    startup(add_arguments)
    startup(configure)
