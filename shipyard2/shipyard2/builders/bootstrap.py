__all__ = [
    'cmd_bootstrap',
]

import logging
import tempfile
from pathlib import Path

import g1.containers.bases
from g1 import scripts
from g1.bases import argparses
from g1.bases.assertions import ASSERT

import shipyard2
from shipyard2 import builders

LOG = logging.getLogger(__name__)


@argparses.begin_parser(
    'bootstrap',
    **shipyard2.make_help_kwargs('build base and builder-base image'),
)
@builders.import_output_arguments(default=True)
@builders.base_image_version_arguments
@argparses.argument(
    'base',
    type=Path,
    help='provide output base image path',
)
@argparses.argument(
    'builder_base',
    type=Path,
    help='provide output builder-base image path',
)
@argparses.end
def cmd_bootstrap(args):
    g1.containers.bases.assert_root_privilege()
    ASSERT.predicate(args.base.parent, Path.is_dir)
    ASSERT.predicate(args.builder_base.parent, Path.is_dir)
    ctr_path = builders.get_ctr_path()
    # Use base output directory for intermediate data.
    with tempfile.TemporaryDirectory(dir=args.base.parent) as tempdir_path:
        tempdir_path = Path(tempdir_path)
        LOG.info('generate base and builder-base under: %s', tempdir_path)
        builder_base_rootfs_path = tempdir_path / 'builder-base'
        scripts.run([
            ctr_path,
            'images',
            'build-base',
            *('--prune-stash-path', builder_base_rootfs_path),
            shipyard2.BASE,
            args.base_version,
            args.base,
        ])
        scripts.run([
            ctr_path,
            'images',
            'build',
            *('--rootfs', builder_base_rootfs_path),
            shipyard2.BUILDER_BASE,
            args.base_version,
            args.builder_base,
        ])
        if args.import_output:
            for path in (args.base, args.builder_base):
                scripts.run([ctr_path, 'images', 'import', path])
    return 0
