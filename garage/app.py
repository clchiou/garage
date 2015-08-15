"""Common application setup."""

__all__ = [
    'ARGS',
    'ARGV',
    'INIT',
    'PARSE',
    'PARSER',

    'D',

    'init',
]

import logging

from startup import startup

from garage.collections import FixedNamespace


#
# PARSER ---> PARSE --+--> ARGS ---> INIT
#                     |
#             ARGV ---+
#
ARGS = 'args'
ARGV = 'argv'
INIT = 'init'
PARSE = 'parse'
PARSER = 'parser'


D = FixedNamespace(
    VERBOSE=0,
)


LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'


@startup
def add_arguments(parser: PARSER) -> PARSE:
    group = parser.add_argument_group(__name__)
    group.add_argument(
        '-v', '--verbose', action='count', default=D.VERBOSE,
        help='verbose output')


@startup
def parse_argv(parser: PARSER, argv: ARGV, _: PARSE) -> ARGS:
    return parser.parse_args(argv[1:])


@startup
def configure_logging(args: ARGS):
    if args.verbose == 0:
        level = logging.WARNING
    elif args.verbose == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG
    logging.basicConfig(level=level, format=LOG_FORMAT)


@startup
def set_globals(args: ARGS):
    D.VERBOSE = args.verbose


@startup
def gate_init(_: ARGS) -> INIT:
    pass


def init():
    # Do nothing at the moment...
    pass
