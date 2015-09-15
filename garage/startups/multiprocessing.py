__all__ = [
    'PYTHON2',
    'init',
]

from startup import startup

from garage import multiprocessing
from garage.functools import run_once

from garage.startups import ARGS, EXIT_STACK, PARSE, PARSER
from garage.startups import components


PYTHON2 = __name__ + ':python2'


def add_arguments(parser: PARSER) -> PARSE:
    group = parser.add_argument_group(multiprocessing.__name__)
    group.add_argument(
        '--python2', default='python2',
        help="""set path or command name of python2 executable""")


def make_python2(args: ARGS, stack: EXIT_STACK) -> PYTHON2:
    return stack.enter_context(multiprocessing.python(args.python2))


@run_once
def init():
    startup(add_arguments)
    components.startup(make_python2)
