__all__ = [
    'main',
]

from g1 import scripts
from g1.bases import argparses
from g1.bases import oses
from g1.bases.assertions import ASSERT

from . import alerts
from . import bases
from . import pod_ops_dirs
from . import tokens
from . import xar_ops_dirs


@argparses.begin_parser(
    'init',
    **argparses.make_help_kwargs('initialize operations repository'),
)
@argparses.argument(
    '--bootstrap',
    action=argparses.StoreBoolAction,
    default=False,
    help='enable bootstrap mode (default: %(default_string)s)',
)
@argparses.end
def cmd_init(args):
    oses.assert_root_privilege()

    # Check pod and XAR dependencies.
    if not args.bootstrap:
        scripts.assert_command_exist('ctr')
    scripts.assert_command_exist('systemctl')
    scripts.assert_command_exist('tar')

    # Check alert dependencies.
    scripts.assert_command_exist('journalctl')
    scripts.assert_command_exist('tail')

    bases.make_dir(bases.get_repo_path(), parents=True)
    alerts.init()
    pod_ops_dirs.init()
    xar_ops_dirs.init()
    tokens.init()

    return 0


@argparses.begin_parser(
    'cleanup',
    **argparses.make_help_kwargs('clean up operations repository'),
)
@argparses.end
def cmd_cleanup():
    oses.assert_root_privilege()
    ops_dirs = pod_ops_dirs.make_ops_dirs()
    ops_dirs.cleanup()
    xar_ops_dirs.make_ops_dirs().cleanup()
    tokens.make_tokens_database().cleanup(ops_dirs)
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
        return cmd_init(args)
    elif args.command == 'cleanup':
        return cmd_cleanup()
    else:
        return ASSERT.unreachable('unknown command: {}', args.command)
