"""Application framework.

This framework is somewhat opinionated; it assumes that applications
need four pieces being initialized before start:
  * contextlib.ExitStack
  * garage.parameters
  * garage.parts
  * logging
(At least in my use cases, they are almost ubiquitous.)
"""

__all__ = [
    'run',
    'using_parts',
    'with_apps',
    'with_argument',
    'with_defaults',
    'with_help',
    'with_input_parts',
    'with_log_level',
    'with_part_names',
    'with_prog',
    'with_selected_makers',
]

import argparse
import contextlib
import logging
import os
import sys
import threading

from garage import parameters
from garage import parts
from garage.assertions import ASSERT
from garage.partdefs import apps


def _ensure_app(main):
    if not isinstance(main, Application):
        main = Application(main)
    return main


def with_prog(prog):
    """Set application name of argparse.ArgumentParser."""
    return lambda main: _ensure_app(main).with_prog(prog)


def with_help(help):
    """Set help message of argparse.ArgumentParser."""
    return lambda main: _ensure_app(main).with_help(help)


def with_argument(*args, **kwargs):
    """Add argument to argparse.ArgumentParser."""
    return lambda main: _ensure_app(main).with_argument(*args, **kwargs)


def with_defaults(**defaults):
    """Update defaults of argparse.ArgumentParser."""
    return lambda main: _ensure_app(main).with_defaults(**defaults)


def with_apps(dest, help, *applications):
    """Set a group of applications under this one."""
    return lambda main: _ensure_app(main).with_apps(dest, help, *applications)


def with_log_level(log_level):
    """Set default logging level."""
    return lambda main: _ensure_app(main).with_log_level(log_level)


def with_input_parts(input_parts):
    """Update input parts for garage.parts.assemble."""
    return lambda main: _ensure_app(main).with_input_parts(input_parts)


def with_part_names(*part_names):
    """Add part names for garage.parts.assemble.

    Call this instead of using_parts when you want to assemble these
    parts but do not want them to be passed to main.
    """
    return lambda main: _ensure_app(main).with_part_names(*part_names)


def with_selected_makers(selected_makers):
    """Update selected maker for garage.parts.assemble."""
    return lambda main: _ensure_app(main).with_selected_makers(selected_makers)


def using_parts(**using_part_names):
    """Assemble and pass these parts to application.main."""
    return lambda main: _ensure_app(main).using_parts(**using_part_names)


class Application:
    """Represent an application."""

    class Group:
        """Represent a group of applications."""

        def __init__(self, dest, help, applications):
            self.dest = dest
            self.help = help
            self.applications = applications

    def __init__(self, main):

        self.main = main

        # For argparse.ArgumentParser.
        self._prog = None
        self._help = None
        self._arguments = []
        self._defaults = {}

        # For other applications.
        self._app_group = None

        # For logging.
        self._log_level = logging.INFO

        # For garage.parts.
        self._part_names = set()
        self._input_parts = {}
        self._selected_makers = {}

        # Let main function use these parts.
        self._using_part_names = []
        self._using_parts = None

    def with_prog(self, prog):
        self._prog = prog
        return self

    def with_help(self, help):
        self._help = help
        return self

    def with_argument(self, *args, **kwargs):
        # This is intended to be used in decorator chains; thus the
        # order is usually reversed (so prepend here, not append).
        self._arguments.insert(0, (args, kwargs))
        return self

    def with_defaults(self, **defaults):
        self._defaults.update(defaults)
        return self

    def with_apps(self, dest, help, *applications):
        applications = [_ensure_app(app) for app in applications]
        ASSERT(applications, 'expect at least one app: %r', applications)
        self._app_group = self.Group(dest, help, applications)
        return self

    def with_log_level(self, log_level):
        self._log_level = log_level
        return self

    def with_input_parts(self, input_parts):
        self._input_parts.update(input_parts)
        return self

    def with_part_names(self, *part_names):
        self._part_names.update(part_names)
        return self

    def with_selected_makers(self, selected_makers):
        self._selected_makers.update(selected_makers)
        return self

    def using_parts(self, **using_part_names):
        self._using_part_names.extend(using_part_names.items())
        return self

    def get_prog(self, argv0=None):
        return self._prog or argv0 or self.main.__name__

    def get_description(self):
        return self.main.__doc__ or sys.modules[self.main.__module__].__doc__

    def get_help(self):
        return self._help or self.get_description()

    def prepare(self, argv, exit_stack):
        """Prepare context for running application.main."""

        # Firstly, configure command-line parser.
        parser = argparse.ArgumentParser(
            prog=self.get_prog(argv[0]),
            description=self.get_description(),
        )
        parser.add_argument(
            '-v', '--verbose',
            action='count', default=0,
            help='increase log level',
        )
        self.configure_parser(parser)
        # Add parameter's command-line arguments at last.
        parameter_list = parameters.add_arguments_to(parser)

        # Secondly, parse command-line arguments.
        args = parser.parse_args(argv[1:])

        # Thirdly, set up the "global" stuff.
        # Configure logging as soon as possible.
        configure_logging(self._log_level, args.verbose)
        # Then read parameter values.
        parameters.read_parameters_from(args, parameter_list)
        # Assemble parts for applications.
        values = self.assemble_parts(exit_stack)
        self.provide_parts(values)

        return args

    def configure_parser(self, parser):
        """Configure argparse.ArgumentParser recursively."""
        parser.set_defaults(**self._defaults)
        for add_argument_args, add_argument_kwargs in self._arguments:
            parser.add_argument(*add_argument_args, **add_argument_kwargs)
        if self._app_group:
            subparsers = parser.add_subparsers(help=self._app_group.help)
            # http://bugs.python.org/issue9253
            subparsers.dest = self._app_group.dest
            subparsers.required = True
            for app in self._app_group.applications:
                subparser = subparsers.add_parser(
                    app.get_prog(),
                    description=app.get_description(),
                    help=app.get_help(),
                )
                subparser.set_defaults(**{self._app_group.dest: app})
                app.configure_parser(subparser)

    def assemble_parts(self, exit_stack):
        """Assemble parts and provide them to using_parts."""
        part_names = set()
        input_parts = {apps.PARTS.exit_stack: exit_stack}
        selected_makers = {}
        self.collect_for_assemble(part_names, input_parts, selected_makers)
        return parts.assemble(
            part_names=part_names,
            input_parts=input_parts,
            selected_makers=selected_makers,
        )

    def collect_for_assemble(self, part_names, input_parts, selected_makers):
        """Collect stuff for assemble() recursively.

        Unfortunately there is no way for me to know which app is going
        to be called, and thus we collect stuff from all sub-apps.
        """

        part_names.update(self._part_names)
        part_names.update(pn for _, pn in self._using_part_names)

        # Sanity check that you do not override "the" exit stack.
        ASSERT.not_in(apps.PARTS.exit_stack, self._input_parts)
        input_parts.update(self._input_parts)

        selected_makers.update(self._selected_makers)

        if self._app_group:
            for app in self._app_group.applications:
                app.collect_for_assemble(
                    part_names, input_parts, selected_makers)

    def provide_parts(self, values):
        """Provide parts to using_parts of this and all sub-apps."""
        ASSERT.none(self._using_parts)
        self._using_parts = {
            name: values[part_name]
            for name, part_name in self._using_part_names
        }
        if self._app_group:
            for app in self._app_group.applications:
                app.provide_parts(values)

    def __call__(self, args):
        """Run the main function."""
        ASSERT(
            self._using_parts is not None,
            'expect context being set up before calling app: %r', self,
        )
        return self.main(args, **self._using_parts)


def run(main, argv=None):
    """Run the application.

    An application can be merely a callable that takes `args` as its
    sole argument and returns and integral status code.
    """
    main = _ensure_app(main)
    with contextlib.ExitStack() as exit_stack:
        args = main.prepare(
            argv=sys.argv if argv is None else argv,
            exit_stack=exit_stack,
        )
        status = main(args)
    sys.exit(status)


def configure_logging(level, verbose):
    """Configure logging."""
    fmt = '%(asctime)s %(threadName)s %(levelname)s %(name)s: %(message)s'
    levels = (logging.WARNING, logging.INFO, logging.DEBUG, TRACE)
    index = min(levels.index(level) + verbose, len(levels) - 1)
    logging.basicConfig(level=levels[index], format=fmt)


# Add a new, finer logging level.
TRACE = logging.DEBUG - 1
logging.addLevelName(TRACE, 'TRACE')

# For prettier logging messages.
threading.main_thread().name = 'main'

# Check if debug logging is enabled.
if os.environ.get('DEBUG', '').lower() not in ('', '0', 'false'):
    configure_logging(logging.DEBUG, 0)
    logging.getLogger(__name__).debug('start at DEBUG level')
