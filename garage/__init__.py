__all__ = [
    'ARGS',
    'ARGV',
    'PARSE',
    'PARSER',

    'D',
]

import logging

from startup import startup


ARGS = 'args'
ARGV = 'argv'
PARSE = 'parse'
PARSER = 'parser'


D = {
    'JOBS': 1,
}


@startup
def add_arguments(parser: PARSER) -> PARSE:
    group = parser.add_argument_group(__name__)
    group.add_argument(
        '-v', '--verbose', action='count', default=0,
        help='verbose output')
    group.add_argument(
        '-j', '--jobs', type=int, default=D['JOBS'],
        help='set number of jobs to run in parallel (default: %(default)s)')


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
    logging.basicConfig(
        level=level,
        format='%(asctime)s: %(levelname)s: %(name)s: %(message)s')


@startup
def set_jobs(args: ARGS):
    D['JOBS'] = args.jobs
