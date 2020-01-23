__all__ = [
    'main',
]

import logging
from pathlib import Path

from g1 import scripts
from g1.bases import argparses
from g1.bases.assertions import ASSERT
from g1.containers import bases as ctr_bases
from g1.containers import scripts as ctr_scripts
from g1.texts import jsons

from . import models

LOG = logging.getLogger(__name__)


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
    ASSERT.predicate(args.bundle, Path.is_dir)
    instruction = jsons.load_dataobject(
        models.XarDeployInstruction,
        args.bundle / models.BUNDLE_DEPLOY_INSTRUCTION_FILENAME,
    )
    if instruction.is_zipapp():
        LOG.info('install zipapp: %s', args.bundle)
        with scripts.using_sudo():
            scripts.cp(
                ASSERT.predicate(
                    args.bundle / models.XAR_BUNDLE_ZIPAPP_FILENAME,
                    Path.is_file,
                ),
                _get_zipapp_target_path(instruction.name),
            )
    else:
        LOG.info('install xar: %s', args.bundle)
        ctr_scripts.ctr_import_image(
            ASSERT.predicate(
                args.bundle / models.XAR_BUNDLE_IMAGE_FILENAME,
                Path.is_file,
            )
        )
        ctr_scripts.ctr_install_xar(
            instruction.name,
            instruction.exec_relpath,
            instruction.image,
        )
    return 0


@argparses.begin_parser(
    'uninstall', **argparses.make_help_kwargs('uninstall zipapp')
)
@argparses.argument('zipapp', help='provide zipapp name')
@argparses.end
def cmd_uninstall(args):
    LOG.info('uninstall zipapp: %s', args.zipapp)
    with scripts.using_sudo():
        scripts.rm(_get_zipapp_target_path(args.zipapp))
    return 0


def _get_zipapp_target_path(name):
    return Path(ctr_bases.PARAMS.xar_runner_script_directory.get()) / name


@argparses.begin_parser('xars', **argparses.make_help_kwargs('manage xar'))
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(cmd_install)
@argparses.include(cmd_uninstall)
@argparses.end
@argparses.end
def main(args):
    if args.command == 'install':
        return cmd_install(args)
    elif args.command == 'uninstall':
        return cmd_uninstall(args)
    else:
        return ASSERT.unreachable('unknown command: {}', args.command)
