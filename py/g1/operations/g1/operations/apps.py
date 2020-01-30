__all__ = [
    'main',
    'run',
]

from startup import startup

import g1.scripts.parts
from g1 import scripts
from g1.apps import bases as apps_bases
from g1.bases import argparses
from g1.bases import oses
from g1.bases.assertions import ASSERT

from . import bases
from . import pod_cmds
from . import pod_ops_dirs
from . import xar_cmds
from . import xar_ops_dirs


@argparses.begin_parser(
    'init',
    **argparses.make_help_kwargs('initialize operations repository'),
)
@argparses.end
def cmd_init():
    oses.assert_root_privilege()
    scripts.assert_command_exist('ctr')
    scripts.assert_command_exist('systemctl')
    scripts.assert_command_exist('tar')
    bases.make_dir(bases.get_repo_path(), parents=True)
    pod_ops_dirs.init()
    xar_ops_dirs.init()
    return 0


@argparses.begin_subparsers_for_subcmds(dest='subject')
@argparses.include(cmd_init)
@argparses.include(pod_cmds.main)
@argparses.include(xar_cmds.main)
@argparses.end
def main(args: apps_bases.LABELS.args, _: g1.scripts.parts.LABELS.setup):
    """Operations tool."""
    if args.subject == 'init':
        return cmd_init()
    elif args.subject == 'pods':
        return pod_cmds.main(args)
    elif args.subject == 'xars':
        return xar_cmds.main(args)
    else:
        return ASSERT.unreachable('unknown subject: {}', args.subject)


def add_arguments(parser: apps_bases.LABELS.parser) -> apps_bases.LABELS.parse:
    argparses.make_argument_parser(main, parser=parser)


def run():
    startup(add_arguments)
    apps_bases.run(main, prog='ops')
