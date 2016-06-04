"""Manage containerized application images."""

import argparse

from ops import scripting
from ops.apps import deploy


def main(argv):
    parser = argparse.ArgumentParser(prog=__name__, description=__doc__)
    subparsers = parser.add_subparsers(help="""Sub-commands.""")
    # http://bugs.python.org/issue9253
    subparsers.dest = 'command'
    subparsers.required = True

    for command in deploy.COMMANDS:
        add_command(subparsers, command)

    args = parser.parse_args(argv[1:])
    scripting.process_arguments(parser, args)
    return args.command(args)


def add_command(subparsers, command):
    parser = subparsers.add_parser(command.__name__, help=command.__doc__)
    parser.set_defaults(command=command)
    scripting.add_arguments(parser)
    command.add_arguments(parser)
