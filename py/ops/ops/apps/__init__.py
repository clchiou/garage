"""Manage containerized application images."""

import argparse

from ops import scripting
from . import base, deploy


def main(argv):
    scripting.ensure_not_root()

    parser = argparse.ArgumentParser(prog=__name__, description=__doc__)
    subparsers = parser.add_subparsers(help="""Sub-commands.""")
    # http://bugs.python.org/issue9253
    subparsers.dest = 'command'
    subparsers.required = True

    for commands in (base.COMMANDS, deploy.COMMANDS):
        for command in commands:
            add_command(subparsers, command)

    args = parser.parse_args(argv[1:])
    scripting.process_arguments(parser, args)
    return args.command(args)


def add_command(subparsers, command):
    name = command.__name__.replace('_', '-')
    parser = subparsers.add_parser(name, help=command.__doc__)
    parser.set_defaults(command=command)
    scripting.add_arguments(parser)
    command.add_arguments(parser)
