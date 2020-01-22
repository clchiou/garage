__all__ = [
    'main',
    'run',
]

from startup import startup

import g1.scripts.parts
from g1.apps import bases
from g1.bases import argparses
from g1.bases.assertions import ASSERT

from . import xars


@argparses.begin_subparsers_for_subcmds(dest='subject')
@argparses.include(xars.main)
@argparses.end
def main(args: bases.LABELS.args, _: g1.scripts.parts.LABELS.setup):
    """Operations tool."""
    if args.subject == 'xars':
        return xars.main(args)
    else:
        return ASSERT.unreachable('unknown subject: {}', args.subject)


def add_arguments(parser: bases.LABELS.parser) -> bases.LABELS.parse:
    argparses.make_argument_parser(main, parser=parser)


def run():
    startup(add_arguments)
    bases.run(main, prog='ops')
