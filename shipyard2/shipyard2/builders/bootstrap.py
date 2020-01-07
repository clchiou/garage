__all__ = [
    'cmd_bootstrap',
]

import logging
import tempfile
from pathlib import Path

import g1.containers.bases
from g1.bases import argparses
from g1.bases.assertions import ASSERT

import shipyard2
from shipyard2 import builders

LOG = logging.getLogger(__name__)


@argparses.begin_parser(
    'bootstrap',
    **builders.make_help_kwargs('build base and builder-base image'),
)
@builders.import_output_arguments(default=True)
@builders.base_image_version_arguments
@argparses.argument(
    'output',
    type=Path,
    help='provide directory for output images',
)
@argparses.end
def cmd_bootstrap(args):
    g1.containers.bases.assert_root_privilege()
    ASSERT.predicate(args.output, Path.is_dir)
    ctr_path = builders.get_ctr_path()
    base_image_path = args.output / 'base.tgz'
    builder_base_image_path = args.output / 'builder-base.tgz'
    with tempfile.TemporaryDirectory(dir=args.output) as tempdir_path:
        tempdir_path = Path(tempdir_path)
        LOG.info('generate base and builder-base under: %s', tempdir_path)
        builder_base_rootfs_path = tempdir_path / 'builder-base'
        builders.run([
            ctr_path,
            'images',
            'build-base',
            *('--prune-stash-path', builder_base_rootfs_path),
            shipyard2.BASE,
            args.base_version,
            base_image_path,
        ])
        builders.run([
            ctr_path,
            'images',
            'build',
            *('--rootfs', builder_base_rootfs_path),
            shipyard2.BUILDER_BASE,
            args.base_version,
            builder_base_image_path,
        ])
        if args.import_output:
            for path in (base_image_path, builder_base_image_path):
                builders.run([ctr_path, 'images', 'import', path])
    return 0
