__all__ = [
    'main',
]

import logging
import sys
from pathlib import Path

from g1.bases import argparses
from g1.bases import oses
from g1.bases.assertions import ASSERT
from g1.texts import columns
from g1.texts.columns import argparses as columns_argparses

from . import models
from . import xar_ops_dirs

LOG = logging.getLogger(__name__)

_XAR_LIST_COLUMNS = frozenset((
    'label',
    'version',
    'zipapp',
))
_XAR_LIST_DEFAULT_COLUMNS = (
    'label',
    'version',
    'zipapp',
)
_XAR_LIST_STRINGIFIERS = {
    'zipapp': lambda active: 'true' if active else 'false',
}
ASSERT.issuperset(_XAR_LIST_COLUMNS, _XAR_LIST_DEFAULT_COLUMNS)
ASSERT.issuperset(_XAR_LIST_COLUMNS, _XAR_LIST_STRINGIFIERS)


@argparses.begin_parser('list', **argparses.make_help_kwargs('list xars'))
@columns_argparses.columnar_arguments(
    _XAR_LIST_COLUMNS, _XAR_LIST_DEFAULT_COLUMNS
)
@argparses.end
def cmd_list(args):
    columnar = columns.Columnar(
        **columns_argparses.make_columnar_kwargs(args),
        stringifiers=_XAR_LIST_STRINGIFIERS,
    )
    with xar_ops_dirs.make_ops_dirs().listing_ops_dirs() as active_ops_dirs:
        for ops_dir in active_ops_dirs:
            columnar.append({
                'label': ops_dir.label,
                'version': ops_dir.version,
                'zipapp': ops_dir.metadata.is_zipapp(),
            })
    columnar.sort(lambda row: (row['label'], row['version']))
    columnar.output(sys.stdout)
    return 0


@argparses.begin_parser(
    'install', **argparses.make_help_kwargs('install xar from a bundle')
)
@argparses.argument(
    'bundle',
    type=Path,
    help='provide path to deployment bundle directory',
)
@argparses.end
def cmd_install(args):
    oses.assert_root_privilege()
    xar_ops_dirs.make_ops_dirs().install(args.bundle)
    return 0


@argparses.begin_parser(
    'uninstall', **argparses.make_help_kwargs('uninstall xar')
)
@argparses.argument(
    'label', type=models.validate_xar_label, help='provide xar label'
)
@argparses.argument(
    'version', type=models.validate_xar_version, help='provide xar version'
)
@argparses.end
def cmd_uninstall(args):
    oses.assert_root_privilege()
    xar_ops_dirs.make_ops_dirs().uninstall(args.label, args.version)
    return 0


@argparses.begin_parser('xars', **argparses.make_help_kwargs('manage xars'))
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(cmd_list)
@argparses.include(cmd_install)
@argparses.include(cmd_uninstall)
@argparses.end
@argparses.end
def main(args):
    if args.command == 'list':
        return cmd_list(args)
    elif args.command == 'install':
        return cmd_install(args)
    elif args.command == 'uninstall':
        return cmd_uninstall(args)
    else:
        return ASSERT.unreachable('unknown command: {}', args.command)
