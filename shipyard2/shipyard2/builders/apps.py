__all__ = [
    'main',
    'run',
]

from startup import startup

import g1.scripts.parts
from g1.apps import bases
from g1.bases import argparses
from g1.bases.assertions import ASSERT

from . import bootstrap
from . import build
from . import merge


@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(bootstrap.cmd_bootstrap)
@argparses.include(build.cmd_build)
@argparses.include(merge.cmd_merge)
@argparses.end
def main(
    args: bases.LABELS.args,
    _: g1.scripts.parts.LABELS.setup,
):
    """Image builder."""
    if args.command == 'bootstrap':
        return bootstrap.cmd_bootstrap(args)
    elif args.command == 'build':
        return build.cmd_build(args)
    elif args.command == 'merge':
        return merge.cmd_merge(args)
    else:
        ASSERT.unreachable('unknown command: {}', args.command)
    return 0


def add_arguments(parser: bases.LABELS.parser) -> bases.LABELS.parse:
    argparses.make_argument_parser(main, parser=parser)


def run():
    startup(add_arguments)
    bases.run(main, prog='builder')
