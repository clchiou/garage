__all__ = [
    'MAKE_PYTHON2',
    'init',
]

import functools

from startup import startup

from garage import multiprocessing
from garage.functools import run_once

import garage.startups
from garage.startups import ARGS, EXIT_STACK, PARSE, PARSER


MAKE_PYTHON2 = __name__ + '#make_python2'


def add_arguments(parser: PARSER) -> PARSE:
    group = parser.add_argument_group(multiprocessing.__name__)
    group.add_argument(
        '--python2', default='python2',
        help="""set path or command name of python2 executable""")


def bind_make_python2(args: ARGS, stack: EXIT_STACK) -> MAKE_PYTHON2:
    return functools.partial(make_python2, stack, args.python2)


def make_python2(stack, python2):
    return stack.enter_context(multiprocessing.python(python2))


@run_once
def init():
    garage.startups.init()
    startup(add_arguments)
    startup(bind_make_python2)
