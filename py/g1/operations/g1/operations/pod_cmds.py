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

_POD_LIST_COLUMNS = frozenset((
    'label',
    'version',
    'id',
))
_POD_LIST_DEFAULT_COLUMNS = (
    'label',
    'version',
    'id',
)
_POD_LIST_STRINGIFIERS = {}
ASSERT.issuperset(_POD_LIST_COLUMNS, _POD_LIST_DEFAULT_COLUMNS)
ASSERT.issuperset(_POD_LIST_COLUMNS, _POD_LIST_STRINGIFIERS)


@argparses.begin_parser('list', **argparses.make_help_kwargs('list pods'))
@columns_argparses.columnar_arguments(
    _POD_LIST_COLUMNS, _POD_LIST_DEFAULT_COLUMNS
)
@argparses.end
def cmd_list(args):
    ops_dirs = pod_ops_dirs.make_pod_ops_dirs()
    ops_dirs.check()
    columnar = columns.Columnar(
        **columns_argparses.make_columnar_kwargs(args),
        stringifiers=_POD_LIST_STRINGIFIERS,
    )
    with ops_dirs.listing_ops_dirs() as active_ops_dirs:
        for ops_dir in active_ops_dirs:
            columnar.append({
                'label': ops_dir.label,
                'version': ops_dir.version,
                'id': ops_dir.metadata.pod_id,
            })
    columnar.sort(lambda row: (row['label'], row['version'], row['id']))
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
@argparses.argument(
    'bundle',
    type=Path,
    help='provide path to deployment bundle directory',
)
@argparses.end
def cmd_install(args):
    oses.assert_root_privilege()
    bundle_dir = pod_ops_dirs.PodBundleDir(args.bundle)
    bundle_dir.check()
    ops_dirs = pod_ops_dirs.make_pod_ops_dirs()
    ops_dirs.check()
    ops_dirs.install(bundle_dir)
    if args.also_start:
        return _start(ops_dirs, bundle_dir.label, bundle_dir.version)
    return 0


@argparses.begin_parser('start', **argparses.make_help_kwargs('start pod'))
@select_pod_arguments
@argparses.end
def cmd_start(args):
    oses.assert_root_privilege()
    ops_dirs = pod_ops_dirs.make_pod_ops_dirs()
    ops_dirs.check()
    return _start(ops_dirs, args.label, args.version)


def _start(ops_dirs, label, version):
    return _ops_dir_apply(
        'start',
        ops_dirs,
        label,
        version,
        lambda ops_dir: ops_dir.activate(),
    )


@argparses.begin_parser('stop', **argparses.make_help_kwargs('stop pod'))
@select_pod_arguments
@argparses.end
def cmd_stop(args):
    oses.assert_root_privilege()
    ops_dirs = pod_ops_dirs.make_pod_ops_dirs()
    ops_dirs.check()
    return _ops_dir_apply(
        'stop',
        ops_dirs,
        args.label,
        args.version,
        lambda ops_dir: ops_dir.deactivate(),
    )


def _ops_dir_apply(cmd, ops_dirs, label, version, func):
    with ops_dirs.using_ops_dir(label, version) as ops_dir:
        if ops_dir is None:
            LOG.error('pods: cannot lock: %s %s', label, version)
            return 1
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
    ops_dirs = pod_ops_dirs.make_pod_ops_dirs()
    ops_dirs.check()
    ops_dirs.uninstall(args.label, args.version)
    return 0


@argparses.begin_parser('pods', **argparses.make_help_kwargs('manage pods'))
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(cmd_list)
@argparses.include(cmd_install)
@argparses.include(cmd_start)
@argparses.include(cmd_stop)
@argparses.include(cmd_uninstall)
@argparses.end
@argparses.end
def main(args):
    if args.command == 'list':
        return cmd_list(args)
    elif args.command == 'install':
        return cmd_install(args)
    elif args.command == 'start':
        return cmd_start(args)
    elif args.command == 'stop':
        return cmd_stop(args)
    elif args.command == 'uninstall':
        return cmd_uninstall(args)
    else:
        return ASSERT.unreachable('unknown command: {}', args.command)
