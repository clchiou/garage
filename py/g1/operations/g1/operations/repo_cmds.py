__all__ = [
    'main',
]

from g1 import scripts
from g1.bases import argparses
from g1.bases import oses
from g1.bases.assertions import ASSERT

from . import bases
from . import pod_ops_dirs
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


@argparses.begin_parser(
    'cleanup',
    **argparses.make_help_kwargs('clean up operations repository'),
)
@argparses.end
def cmd_cleanup():
    oses.assert_root_privilege()
    pod_ops_dirs.make_ops_dirs().cleanup()
    xar_ops_dirs.make_ops_dirs().cleanup()
    return 0


@argparses.begin_parser(
    'repos',
    **argparses.make_help_kwargs('manage operations repository'),
)
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(cmd_init)
@argparses.include(cmd_cleanup)
@argparses.end
@argparses.end
def main(args):
    if args.command == 'init':
        return cmd_init()
    elif args.command == 'cleanup':
        return cmd_cleanup()
    else:
        return ASSERT.unreachable('unknown command: {}', args.command)
