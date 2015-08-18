"""Initialize/configure modules with startup.

The basic startup dependency graph is:

  PARSER ---> PARSE --+--> ARGS ---> CONFIGURED
                      |
              ARGV ---+
"""

__all__ = [
    'ARGS',
    'ARGV',
    'CONFIGURED',
    'PARSE',
    'PARSER',
    'init',
]

from startup import startup

from garage.functools import run_once


ARGS = 'args'
ARGV = 'argv'
CONFIGURED = 'configured'
PARSE = 'parse'
PARSER = 'parser'


def parse_argv(parser: PARSER, argv: ARGV, _: PARSE) -> ARGS:
    return parser.parse_args(argv[1:])


@run_once
def init():
    startup(parse_argv)
