"""Base runner for applications."""

__all__ = [
    # Public interface.
    'LABELS',
    'run',
    # Helpers for implementing runners.
    'prepare_startup',
    'do_startup',
]

import argparse
import inspect
import contextlib
import sys

from startup import startup

from g1.bases import labels
from g1.bases.assertions import ASSERT

from . import loggers

LABELS = labels.make_labels(
    __name__,
    'args',
    'args_not_validated',
    'argv',
    'parser',
    # Although not all applications need an ``ExitStack``, I find it
    # very useful in almost all use cases, and so it is provided.
    'exit_stack',
    # In case you want to change the main function dynamically...
    'main',
    # Labels for sequencing application startup.
    'parse',
    'validate_args',
)

#
# Application startup.
#


@startup
def parse_argv(
    parser: LABELS.parser,
    argv: LABELS.argv,
    _: LABELS.parse,
) -> LABELS.args_not_validated:
    return parser.parse_args(argv[1:])


@startup
def wait_for_args_validation(
    args: LABELS.args_not_validated,
    _: LABELS.validate_args,
) -> LABELS.args:
    return args


startup.add_func(
    loggers.add_arguments,
    {
        'parser': LABELS.parser,
        'return': LABELS.parse,
    },
)

startup.add_func(
    loggers.configure_logging,
    {'args': LABELS.args},
)

#
# Public interface.
#


def run(main, argv=None):
    prepare_startup(main, argv)
    with contextlib.ExitStack() as exit_stack:
        startup.set(LABELS.exit_stack, exit_stack)
        main, kwargs = do_startup()
        status = main(**kwargs)
    sys.exit(status)


#
# Helpers for implementing runners.
#


def prepare_startup(main, argv):
    if argv is None:
        argv = sys.argv
    startup.set(LABELS.argv, argv)
    startup.set(LABELS.main, main)
    startup.set(LABELS.parser, make_parser(main, argv))
    # Trick to make ``parse`` and ``validate_args`` "optional".
    startup.set(LABELS.parse, None)
    startup.set(LABELS.validate_args, None)


def make_parser(main, argv):

    package = sys.modules[main.__module__].__package__

    if main.__module__ != '__main__':
        prog = main.__module__
    elif package:
        prog = package
    else:
        prog = argv[0]

    if main.__doc__:
        description = main.__doc__
    elif sys.modules[main.__module__].__doc__:
        description = sys.modules[main.__module__].__doc__
    elif package and sys.modules[package].__doc__:
        description = sys.modules[package].__doc__
    else:
        description = None

    return argparse.ArgumentParser(prog=prog, description=description)


def do_startup():
    varz = startup.call()
    main = varz[LABELS.main]
    kwargs = {}
    for parameter in inspect.signature(main).parameters.values():
        if parameter.annotation is parameter.empty:
            ASSERT.is_not(parameter.default, parameter.empty)
        else:
            kwargs[parameter.name] = varz[parameter.annotation]
    return main, kwargs
