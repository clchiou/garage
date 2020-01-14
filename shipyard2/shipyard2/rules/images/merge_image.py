__all__ = [
    'merge_image',
]

import contextlib
import logging
import tempfile
from pathlib import Path

from g1 import scripts

from . import utils

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


def merge_image(
    *,
    name,
    version,
    builder_images,
    filters,
    output,
):
    rootfs_paths = [
        utils.ctr_get_rootfs_path(kind, args) for kind, args in builder_images
    ]
    rootfs_paths.append(
        utils.ctr_get_rootfs_path(
            'nv',
            (utils.get_builder_name(name), version),
        )
    )
    filter_rules = _get_filter_rules(filters)
    with contextlib.ExitStack() as stack:
        tempdir_path = stack.enter_context(
            tempfile.TemporaryDirectory(dir=output.parent)
        )
        output_rootfs_path = Path(tempdir_path) / 'rootfs'
        stack.callback(utils.sudo_rm, output_rootfs_path)
        LOG.info('generate application image under: %s', output_rootfs_path)
        # NOTE: Do NOT overlay-mount these rootfs (and then rsync from
        # the overlay) because the overlay does not include base and
        # base-builder, and thus some tombstone files may not be copied
        # correctly (I don't know why but rsync complains about this).
        # For now our workaround is to rsync each rootfs sequentially.
        with scripts.using_sudo():
            for rootfs_path in rootfs_paths:
                utils.rsync(rootfs_path, output_rootfs_path, filter_rules)
        utils.ctr_build_image(name, version, output_rootfs_path, output)


def _get_filter_rules(filters):
    return [
        # Log which files are included/excluded due to filter rules.
        '--debug=FILTER2',
        *('--%s=%s' % pair for pair in _DEFAULT_FILTERS),
        *('--%s=%s' % pair for pair in filters),
    ]
