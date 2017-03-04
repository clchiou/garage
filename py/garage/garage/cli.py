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
    'sub_command',
    'verbosity',
]

import argparse
import contextlib
import functools
import sys

from startup import startup

import garage.components


DEFAULT_SUBCMDS_DEST = 'sub_command'


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
def component(comp):
    return functools.partial(DecoratorChain.component, comp=comp)


@make_decorator
def sub_command_group(dest=DEFAULT_SUBCMDS_DEST, help=None):
    return functools.partial(
        DecoratorChain.sub_command_group, dest=dest, help=help)


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
        self._components = []
        self._subcmds_dest = DEFAULT_SUBCMDS_DEST
        self._subcmds_help = None
        self._subcmds = []
        self._verbosity = 1

    def argument(self, args, kwargs):
        self._arguments.append((args, kwargs))
        return self

    def component(self, comp):
        self._components.append(comp)
        return self

    def sub_command_group(self, dest, help):
        self._subcmds_dest = dest
        self._subcmds_help = help
        return self

    def sub_command(self, subcmd):
        assert isinstance(subcmd, EntryPoint)
        self._subcmds.append(subcmd)
        return self

    def verbosity(self, verbosity_):
        self._verbosity = verbosity_
        return self

    def build(self, name=None, help=None):
        # Make copies (also remember that you add elements to these
        # lists in reverse order and so you have to reverse them here)
        return EntryPoint(
            self._entry_point,
            name,
            help,
            list(reversed(self._arguments)),
            list(reversed(self._components)),
            self._subcmds_dest,
            self._subcmds_help,
            list(reversed(self._subcmds)),
            self._verbosity,
        )


class EntryPoint:

    def __init__(self,
                 entry_point,
                 name,
                 help,
                 arguments,
                 components,
                 subcmds_dest,
                 subcmds_help,
                 subcmds,
                 verbosity_):
        self._entry_point = entry_point
        self._name = name
        self._help = help
        self._arguments = arguments
        self._components = components
        self._subcmds_dest = subcmds_dest
        self._subcmds_help = subcmds_help
        self._subcmds = subcmds
        self._verbosity = verbosity_
        self._varz = None

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

    def __call__(self):
        with contextlib.ExitStack() as exit_stack:
            self._prepare(startup, sys.argv, exit_stack)
            rc = self.call_entry_point()
        sys.exit(rc)

    def _prepare(self, startup_, argv, exit_stack):
        """Prepare the context and call initialize()."""

        parser = argparse.ArgumentParser(
            prog=self.prog, description=self.description)

        startup_.set(garage.components.ARGV, argv)
        startup_.set(garage.components.EXIT_STACK, exit_stack)
        startup_.set(garage.components.PARSER, parser)
        startup_(garage.components.parse_argv)

        # Use set() to filter out duplicated components
        comps = set(self.initialize(parser))
        if self._verbosity is not None:
            from garage.startups.logging import LoggingComponent
            comps.add(LoggingComponent(self._verbosity))
        comps = [comp() if isinstance(comp, type) else comp for comp in comps]

        for comp in garage.components.find_closure(*comps):
            garage.components.bind(comp, startup=startup_)

        self.set_varz(startup_.call())

    def initialize(self, parser):
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
                subparser.set_defaults(**{
                    self._subcmds_dest: functools.partial(
                        self.call_sub_command_entry_point, subcmd)
                })
                # Recursively call into subcmd.initialize()
                yield from subcmd.initialize(subparser)
        yield from self._components

    def set_varz(self, varz):
        assert self._varz is None or self._varz is varz
        self._varz = varz

    def call_entry_point(self):
        assert self._varz is not None
        return self._entry_point(**{
            arg: self._varz[var]
            for arg, var in self._entry_point.__annotations__.items()
            if arg != 'return'
        })

    def call_sub_command_entry_point(self, subcmd):
        assert self._varz is not None
        subcmd.set_varz(self._varz)  # Propagate varz
        return subcmd.call_entry_point()
