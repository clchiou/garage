__all__ = [
    'main',
    'run',
]

from startup import startup

import g1.scripts.parts
from g1.apps import bases as apps_bases
from g1.bases import argparses
from g1.bases import oses
from g1.bases.assertions import ASSERT

from . import bases
from . import xar_cmds
from . import xar_ops_dirs


@argparses.begin_parser(
    'init',
    **argparses.make_help_kwargs('initialize operations repository'),
)
@argparses.end
def cmd_init():
    oses.assert_root_privilege()
    bases.make_dir(bases.get_repo_path(), parents=True)
    ops_dirs = xar_ops_dirs.make_xar_ops_dirs()
    ops_dirs.init()
    ops_dirs.check()
    return 0


@argparses.begin_subparsers_for_subcmds(dest='subject')
@argparses.include(cmd_init)
@argparses.include(xar_cmds.main)
@argparses.end
def main(args: apps_bases.LABELS.args, _: g1.scripts.parts.LABELS.setup):
    """Operations tool."""
    if args.subject == 'init':
        return cmd_init()
    elif args.subject == 'xars':
        return xar_cmds.main(args)
    else:
        return ASSERT.unreachable('unknown subject: {}', args.subject)


def add_arguments(parser: apps_bases.LABELS.parser) -> apps_bases.LABELS.parse:
    argparses.make_argument_parser(main, parser=parser)


def run():
    startup(add_arguments)
    apps_bases.run(main, prog='ops')
