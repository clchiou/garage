__all__ = [
    'cmd_merge',
]

import contextlib
import logging
import tempfile
from pathlib import Path

import g1.containers.bases
import g1.containers.images
from g1.bases import argparses
from g1.bases.assertions import ASSERT

from shipyard2 import builders

LOG = logging.getLogger(__name__)

_DEFAULT_FILTERS = (
    # Do not leak any source codes to the application image.
    # Keep this in sync with //bases:build.
    ('exclude', '/home/plumber/drydock'),
    ('exclude', '/usr/src'),
    # Include only relevant files under /etc.
    ('include', '/etc/'),
    ('include', '/etc/group'),
    ('include', '/etc/group-'),
    ('include', '/etc/gshadow'),
    ('include', '/etc/gshadow-'),
    ('include', '/etc/inputrc'),
    ('include', '/etc/ld.so.cache'),
    ('include', '/etc/passwd'),
    ('include', '/etc/passwd-'),
    ('include', '/etc/shadow'),
    ('include', '/etc/shadow-'),
    ('include', '/etc/ssl'),
    ('include', '/etc/subgid'),
    ('include', '/etc/subgid-'),
    ('include', '/etc/subuid'),
    ('include', '/etc/subuid-'),
    ('include', '/etc/sudoers.d/'),
    ('include', '/etc/sudoers.d/**'),
    ('exclude', '/etc/**'),
    # Exclude distro binaries from application image (note that base
    # image includes a base set of distro binaries).
    ('exclude', '/bin'),
    ('exclude', '/sbin'),
    ('exclude', '/usr/bin'),
    ('exclude', '/usr/sbin'),
    # Exclude headers.
    ('exclude', '/usr/include'),
    ('exclude', '/usr/local/include'),
    # Exclude distro systemd files.
    ('exclude', '/lib/systemd'),
    ('exclude', '/usr/lib/systemd'),
    # In general, don't exclude distro libraries since we might depend
    # on them, except these libraries.
    ('exclude', '/usr/lib/apt'),
    ('exclude', '/usr/lib/gcc'),
    ('exclude', '/usr/lib/git-core'),
    ('exclude', '/usr/lib/python*'),
    ('exclude', '/usr/lib/**/*perl*'),
    # Exclude these to save more space.
    ('exclude', '/usr/share'),  # Do we need (portion of) this?
    ('exclude', '/var'),
)


@argparses.begin_parser(
    'merge',
    **builders.make_help_kwargs(
        'merge intermediate builder images into application image'
    ),
)
@builders.select_image_arguments
@argparses.argument(
    '--include-path',
    action=argparses.AppendConstAndValueAction,
    dest='filter',
    const='include',
    help='add output path filter for inclusion'
)
@argparses.argument(
    '--exclude-path',
    action=argparses.AppendConstAndValueAction,
    dest='filter',
    const='exclude',
    help='add output path filter for exclusion'
)
@builders.import_output_arguments(default=False)
@g1.containers.images.image_output_arguments
@argparses.end
def cmd_merge(args):
    g1.containers.bases.assert_root_privilege()
    ASSERT.not_empty(args.image)
    ASSERT.not_predicate(args.output, g1.containers.bases.lexists)
    ctr_path = builders.get_ctr_path()
    rootfs_paths = _get_rootfs_paths(args)
    filter_rules = _get_filter_rules(args)
    with contextlib.ExitStack() as stack:
        tempdir_path = Path(
            stack.enter_context(
                tempfile.TemporaryDirectory(dir=args.output.parent)
            )
        )
        LOG.info('generate application image under: %s', tempdir_path)
        merged = tempdir_path / 'merged'
        merged.mkdir()
        filtered = tempdir_path / 'filtered'
        filtered.mkdir()
        _mount_overlay(rootfs_paths, merged)
        stack.callback(_umount_overlay, merged)
        if not builders.PARAMS.dry_run.get():
            g1.containers.bases.rsync_copy(merged, filtered, filter_rules)
        builders.run([
            ctr_path,
            'images',
            'build',
            *('--rootfs', filtered),
            args.name,
            args.version,
            args.output,
        ])
        if args.import_output:
            builders.run([ctr_path, 'images', 'import', args.output])
    return 0


def _get_rootfs_paths(args):
    rootfs_paths = []
    for image in args.image or ():
        if image[0] == 'id':
            image_id = image[1]
        elif image[0] == 'nv':
            image_id = g1.containers.images.find_id(
                name=g1.containers.images.validate_name(image[1][0]),
                version=g1.containers.images.validate_version(image[1][1]),
            )
        elif image[0] == 'tag':
            image_id = g1.containers.images.find_id(tag=image[1])
        else:
            ASSERT.unreachable('unknown image arg: {}', image)
        rootfs_paths.append(
            g1.containers.images.get_rootfs_path(
                g1.containers.images.get_image_dir_path(image_id)
            )
        )
    return rootfs_paths


def _get_filter_rules(args):
    return [
        # Log which files are included/excluded due to filter rules.
        '--debug=FILTER2',
        *('--%s=%s' % pair for pair in _DEFAULT_FILTERS),
        *('--%s=%s' % pair for pair in args.filter or ()),
    ]


def _mount_overlay(rootfs_paths, mount_point):
    # Call reversed() because in overlay file system, lower directories
    # are ordered from high to low.
    builders.run([
        'mount',
        *('-t', 'overlay'),
        *('-o', 'lowerdir=%s' % ':'.join(map(str, reversed(rootfs_paths)))),
        'overlay',
        mount_point,
    ])


def _umount_overlay(mount_point):
    builders.run(['umount', mount_point])
    # Just a sanity check that rootfs is really unmounted.
    ASSERT.predicate(mount_point, g1.containers.bases.is_empty_dir)
