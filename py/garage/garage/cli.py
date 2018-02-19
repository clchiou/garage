"""\
Helpers for constructing command-line program entry points.

Features:
  * Integrate with garage.components
  * Support nested sub-commands
  * Use single-stage startup
"""

__all__ = [
    'command',
    'argument',
    'component',
    'defaults',
    'sub_command_info',
    'sub_command',
    'verbosity',
    # Helpers
    'combine_decorators',
]

import argparse
import contextlib
import functools
import sys

from startup import startup

from garage.assertions import ASSERT
from garage.collections import unique
import garage.components


DEFAULT_SUBCMDS_DEST = 'sub_command'


def combine_decorators(*decorators):
    return lambda entry_point: functools.reduce(
        lambda entry_point, decorator: decorator(entry_point),
        reversed(decorators),
        entry_point,
    )


def make_decorator(make_method):
    def decorator(*args, **kwargs):
        return functools.partial(_apply, make_method(*args, **kwargs))
    return decorator


def _apply(method, chain):
    if not isinstance(chain, DecoratorChain):
        chain = DecoratorChain(chain)
    return method(chain)


@make_decorator
def command(name=None, help=None):
    return functools.partial(DecoratorChain.build, name=name, help=help)


@make_decorator
def argument(*args, **kwargs):
    return functools.partial(
        DecoratorChain.argument, args=args, kwargs=kwargs)


@make_decorator
def defaults(**kwargs):
    return functools.partial(DecoratorChain.defaults, kwargs=kwargs)


@make_decorator
def component(comp):
    return functools.partial(DecoratorChain.component, comp=comp)


@make_decorator
def sub_command_info(dest=DEFAULT_SUBCMDS_DEST, help=None):
    return functools.partial(
        DecoratorChain.sub_command_info, dest=dest, help=help)


@make_decorator
def sub_command(subcmd):
    return functools.partial(
        DecoratorChain.sub_command, subcmd=subcmd)


@make_decorator
def verbosity(verbosity_):
    return functools.partial(
        DecoratorChain.verbosity, verbosity_=verbosity_)


class DecoratorChain:

    def __init__(self, entry_point):
        self._entry_point = entry_point
        self._arguments = []
        self._defaults = None
        self._components = []
        self._subcmds_dest = DEFAULT_SUBCMDS_DEST
        self._subcmds_help = None
        self._subcmds = []
        self._verbosity = 1

    def argument(self, args, kwargs):
        self._arguments.append((args, kwargs))
        return self

    def defaults(self, kwargs):
        self._defaults = kwargs
        return self

    def component(self, comp):
        self._components.append(comp)
        return self

    def sub_command_info(self, dest, help):
        self._subcmds_dest = dest
        self._subcmds_help = help
        return self

    def sub_command(self, subcmd):
        ASSERT.type_of(subcmd, Command)
        self._subcmds.append(subcmd)
        return self

    def verbosity(self, verbosity_):
        self._verbosity = verbosity_
        return self

    def build(self, name=None, help=None):
        # Make copies (also remember that you add elements to these
        # lists in reverse order and so you have to reverse them here)
        cmd = Command(
            self._entry_point,
            name,
            help,
            list(reversed(self._arguments)),
            dict(self._defaults or {}),
            list(reversed(self._components)),
            self._subcmds_dest,
            self._subcmds_help,
            list(reversed(self._subcmds)),
            self._verbosity,
        )
        return functools.wraps(self._entry_point)(cmd)


# The global context of the entire program
CONTEXT = None


class Command:

    def __init__(self,
                 entry_point,
                 name,
                 help,
                 arguments,
                 defaults,
                 components,
                 subcmds_dest,
                 subcmds_help,
                 subcmds,
                 verbosity_):
        self._entry_point = entry_point
        self._name = name
        self._help = help
        self._arguments = arguments
        self._defaults = defaults
        self._components = components
        self._subcmds_dest = subcmds_dest
        self._subcmds_help = subcmds_help
        self._subcmds = subcmds
        self._verbosity = verbosity_

    @property
    def prog(self):
        return self._name or self._entry_point.__name__

    @property
    def description(self):
        return (self._entry_point.__doc__ or
                sys.modules[self._entry_point.__module__].__doc__)

    @property
    def help(self):
        return self._help or self.description

    def __call__(self, **kwargs):
        global CONTEXT
        if CONTEXT is None:
            # Assume we are the main program entry point
            with contextlib.ExitStack() as exit_stack:
                CONTEXT = self._prepare(startup, sys.argv, exit_stack)
                rc = self._main(kwargs)
            sys.exit(rc)
        else:
            # Assume we are called from the main program entry point
            return self._main(kwargs)

    def _prepare(self, startup_, argv, exit_stack):
        """Prepare the context and call _initialize()."""

        parser = argparse.ArgumentParser(
            prog=self.prog, description=self.description)
        parser.set_defaults(**self._defaults)

        startup_.set(garage.components.ARGV, argv)
        startup_.set(garage.components.EXIT_STACK, exit_stack)
        startup_.set(garage.components.PARSER, parser)
        startup_(garage.components.parse_argv)

        # Filter out duplicated components (use unique because it
        # preserves the original ordering)
        comps = unique(self._initialize(parser))
        if self._verbosity is not None:
            from garage.startups.logging import LoggingComponent
            comps.append(LoggingComponent(self._verbosity))

        for comp in garage.components.find_closure(*comps):
            garage.components.bind(comp, startup=startup_)

        return startup_.call()

    def _initialize(self, parser):
        """Initialize command and sub-commands recursively and return
           all components.
        """
        for args, kwargs in self._arguments:
            parser.add_argument(*args, **kwargs)
        if self._subcmds:
            subparsers = parser.add_subparsers(help=self._subcmds_help)
            # http://bugs.python.org/issue9253
            subparsers.dest = self._subcmds_dest
            subparsers.required = True
            for subcmd in self._subcmds:
                subparser = subparsers.add_parser(
                    subcmd.prog,
                    description=subcmd.description,
                    help=subcmd.help,
                )
                subparser.set_defaults(
                    **{self._subcmds_dest: subcmd},
                    **subcmd._defaults,
                )
                # Recursively call into subcmd._initialize()
                yield from subcmd._initialize(subparser)
        yield from self._components

    def _main(self, kwargs):
        injected_kwargs = {
            arg: CONTEXT[var]
            for arg, var in self._entry_point.__annotations__.items()
            if arg != 'return'
        }
        # arguments in kwargs takes precedence over injected arguments
        injected_kwargs.update(kwargs)
        return self._entry_point(**injected_kwargs)
