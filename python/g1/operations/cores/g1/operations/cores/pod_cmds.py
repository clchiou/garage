__all__ = [
    'main',
]

import logging
import sys
from pathlib import Path

from g1.bases import argparses
from g1.bases import functionals
from g1.bases import oses
from g1.bases.assertions import ASSERT
from g1.containers import models as ctr_models
from g1.texts import columns
from g1.texts.columns import argparses as columns_argparses

from . import models
from . import pod_ops_dirs
from . import systemds

LOG = logging.getLogger(__name__)

select_pod_arguments = functionals.compose(
    argparses.argument(
        'label',
        type=models.validate_pod_label,
        help='provide pod label',
    ),
    argparses.argument(
        'version',
        type=ctr_models.validate_pod_version,
        help='provide pod version',
    ),
)

select_unit_arguments = functionals.compose(
    argparses.begin_mutually_exclusive_group(required=False),
    argparses.argument(
        '--unit',
        action='append',
        help='add systemd unit name to be started',
    ),
    argparses.argument(
        '--unit-all',
        action=argparses.StoreBoolAction,
        default=False,
        help='start all systemd units (default: %(default_string)s)',
    ),
    argparses.end,
)


def bool_to_str(b):
    return 'true' if b else 'false'


_POD_LIST_COLUMNS = frozenset((
    'label',
    'version',
    'id',
    'name',
    'unit',
    'auto-start',
    'auto-stop',
    'enabled',
    'active',
))
_POD_LIST_DEFAULT_COLUMNS = (
    'label',
    'version',
    'id',
    'name',
    'active',
)
_POD_LIST_STRINGIFIERS = {
    'auto-start': bool_to_str,
    'auto-stop': bool_to_str,
    'enabled': bool_to_str,
    'active': bool_to_str,
}
ASSERT.issuperset(_POD_LIST_COLUMNS, _POD_LIST_DEFAULT_COLUMNS)
ASSERT.issuperset(_POD_LIST_COLUMNS, _POD_LIST_STRINGIFIERS)


@argparses.begin_parser('list', **argparses.make_help_kwargs('list pods'))
@columns_argparses.columnar_arguments(
    _POD_LIST_COLUMNS, _POD_LIST_DEFAULT_COLUMNS
)
@argparses.end
def cmd_list(args):
    columnar = columns.Columnar(
        **columns_argparses.make_columnar_kwargs(args),
        stringifiers=_POD_LIST_STRINGIFIERS,
    )
    with pod_ops_dirs.make_ops_dirs().listing_ops_dirs() as active_ops_dirs:
        for ops_dir in active_ops_dirs:
            for config in ops_dir.metadata.systemd_unit_configs:
                columnar.append({
                    'label': ops_dir.label,
                    'version': ops_dir.version,
                    'id': config.pod_id,
                    'name': config.name,
                    'unit': config.unit_name,
                    'auto-start': config.auto_start,
                    'auto-stop': config.auto_stop,
                    'enabled': systemds.is_enabled(config),
                    'active': systemds.is_active(config),
                })
    columnar.sort(lambda row: (row['label'], row['version'], row['name']))
    columnar.output(sys.stdout)
    return 0


@argparses.begin_parser(
    'install', **argparses.make_help_kwargs('install pod from a bundle')
)
@argparses.argument(
    '--also-start',
    action=argparses.StoreBoolAction,
    default=True,
    help='also start pod after install (default: %(default_string)s)',
)
@select_unit_arguments
@argparses.argument(
    'bundle',
    type=Path,
    help='provide path to deployment bundle directory',
)
@argparses.end
def cmd_install(args):
    oses.assert_root_privilege()
    bundle_dir = pod_ops_dirs.PodBundleDir(args.bundle)
    ops_dirs = pod_ops_dirs.make_ops_dirs()
    ops_dirs.install(bundle_dir.path)
    if args.also_start:
        return _start(ops_dirs, bundle_dir.label, bundle_dir.version, args)
    return 0


@argparses.begin_parser('start', **argparses.make_help_kwargs('start pod'))
@select_unit_arguments
@select_pod_arguments
@argparses.end
def cmd_start(args):
    oses.assert_root_privilege()
    return _start(pod_ops_dirs.make_ops_dirs(), args.label, args.version, args)


def _start(ops_dirs, label, version, args):
    return _ops_dir_apply(
        'start',
        ops_dirs,
        label,
        version,
        lambda ops_dir: ops_dir.start(
            unit_names=args.unit,
            all_units=args.unit_all,
        ),
    )


@argparses.begin_parser('restart', **argparses.make_help_kwargs('restart pod'))
@select_unit_arguments
@select_pod_arguments
@argparses.end
def cmd_restart(args):
    oses.assert_root_privilege()
    return _ops_dir_apply(
        'restart',
        pod_ops_dirs.make_ops_dirs(),
        args.label,
        args.version,
        lambda ops_dir: ops_dir.restart(
            unit_names=args.unit,
            all_units=args.unit_all,
        ),
    )


@argparses.begin_parser('stop', **argparses.make_help_kwargs('stop pod'))
@select_unit_arguments
@select_pod_arguments
@argparses.end
def cmd_stop(args):
    oses.assert_root_privilege()
    return _ops_dir_apply(
        'stop',
        pod_ops_dirs.make_ops_dirs(),
        args.label,
        args.version,
        lambda ops_dir: ops_dir.stop(
            unit_names=args.unit,
            all_units=args.unit_all,
        ),
    )


def _ops_dir_apply(cmd, ops_dirs, label, version, func):
    with ops_dirs.using_ops_dir(label, version) as ops_dir:
        LOG.info('pods %s: %s %s', cmd, label, version)
        func(ops_dir)
    return 0


@argparses.begin_parser(
    'uninstall', **argparses.make_help_kwargs('uninstall pod')
)
@select_pod_arguments
@argparses.end
def cmd_uninstall(args):
    oses.assert_root_privilege()
    pod_ops_dirs.make_ops_dirs().uninstall(args.label, args.version)
    return 0


@argparses.begin_parser('pods', **argparses.make_help_kwargs('manage pods'))
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(cmd_list)
@argparses.include(cmd_install)
@argparses.include(cmd_start)
@argparses.include(cmd_restart)
@argparses.include(cmd_stop)
@argparses.include(cmd_uninstall)
@argparses.end
@argparses.end
def main(args):
    commands = {
        'list': cmd_list,
        'install': cmd_install,
        'start': cmd_start,
        'restart': cmd_restart,
        'stop': cmd_stop,
        'uninstall': cmd_uninstall,
    }
    if args.command not in commands:
        return ASSERT.unreachable('unknown command: {}', args.command)
    return commands[args.command](args)
