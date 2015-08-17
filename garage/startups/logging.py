"""Initialize logging."""

__all__ = [
    'init',
]

import logging

from startup import startup

from garage import startups


LOG_FORMAT = '%(asctime)s %(threadName)s %(levelname)s %(name)s: %(message)s'


def add_arguments(parser: startups.PARSER) -> startups.PARSE:
    group = parser.add_argument_group(__name__)
    group.add_argument(
        '-v', '--verbose', action='count', default=0,
        help='verbose output')


def configure(args: startups.ARGS) -> startups.CONFIGURED:
    if args.verbose == 0:
        level = logging.WARNING
    elif args.verbose == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG
    logging.basicConfig(level=level, format=LOG_FORMAT)


def init():
    startup(add_arguments)
    startup(configure)
