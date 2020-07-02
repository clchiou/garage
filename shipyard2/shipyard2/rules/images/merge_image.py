__all__ = [
    'DEFAULT_FILTERS',
    'DEFAULT_XAR_FILTERS',
    'merge_image',
]

import contextlib
import logging
import tempfile
from pathlib import Path

from g1 import scripts
from g1.containers import models
from g1.containers import scripts as ctr_scripts

from . import utils

LOG = logging.getLogger(__name__)

DEFAULT_FILTERS = (
    # Do not leak any source codes to the application image.
    # Keep drydock path in sync with //bases:build.
    ('exclude', '/home/plumber/drydock'),
    ('exclude', '/home/plumber/.gradle'),
    ('exclude', '/home/plumber/.python_history'),
    ('exclude', '/home/plumber/.wget-hsts'),
    ('exclude', '/root/.cache'),
    ('exclude', '/usr/src'),
    # Include only relevant files under /etc.
    ('include', '/etc/'),
    # We use distro java at the moment.
    ('include', '/etc/alternatives/'),
    ('include', '/etc/alternatives/java'),
    ('include', '/etc/java*'),
    ('include', '/etc/java*/**'),
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
    # We use distro java at the moment.
    ('include', '/usr/bin/'),
    ('include', '/usr/bin/java'),
    ('exclude', '/usr/bin/**'),
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

# For XAR images, we only include a few selected directories, and
# exclude everything else.
#
# To support Python, we include our CPython under /usr/local in the XAR
# image (like our pod image).  An alternative is to use venv to install
# our codebase, but this seems to be too much effort; so we do not take
# this approach for now.
#
# We do not include /usr/bin/java (symlink to /etc/alternatives) for
# now.  If you want to use Java, you have to directly invoke it under
# /usr/lib/jvm/...
DEFAULT_XAR_FILTERS = (
    ('include', '/usr/'),
    ('include', '/usr/lib/'),
    ('exclude', '/usr/lib/**/*perl*'),
    ('include', '/usr/lib/jvm/'),
    ('include', '/usr/lib/jvm/**'),
    ('include', '/usr/lib/x86_64-linux-gnu/'),
    ('include', '/usr/lib/x86_64-linux-gnu/**'),
    ('include', '/usr/local/'),
    ('include', '/usr/local/bin/'),
    ('include', '/usr/local/bin/*'),
    ('include', '/usr/local/lib/'),
    ('include', '/usr/local/lib/**'),
    ('exclude', '**'),
)


@scripts.using_sudo()
def merge_image(
    *,
    name,
    version,
    builder_images,
    default_filters,
    filters,
    output,
):
    rootfs_paths = [
        ctr_scripts.ctr_get_image_rootfs_path(image)
        for image in builder_images
    ]
    rootfs_paths.append(
        ctr_scripts.ctr_get_image_rootfs_path(
            models.PodConfig.Image(
                name=utils.get_builder_name(name),
                version=version,
            )
        )
    )
    filter_rules = _get_filter_rules(default_filters, filters)
    with contextlib.ExitStack() as stack:
        tempdir_path = stack.enter_context(
            tempfile.TemporaryDirectory(dir=output.parent)
        )
        output_rootfs_path = Path(tempdir_path) / 'rootfs'
        stack.callback(scripts.rm, output_rootfs_path, recursive=True)
        LOG.info('generate application image under: %s', output_rootfs_path)
        # NOTE: Do NOT overlay-mount these rootfs (and then rsync from
        # the overlay) because the overlay does not include base and
        # base-builder, and thus some tombstone files may not be copied
        # correctly (I don't know why but rsync complains about this).
        # For now our workaround is to rsync each rootfs sequentially.
        for rootfs_path in rootfs_paths:
            utils.rsync(rootfs_path, output_rootfs_path, filter_rules)
        ctr_scripts.ctr_build_image(name, version, output_rootfs_path, output)


def _get_filter_rules(default_filters, filters):
    return [
        # Log which files are included/excluded due to filter rules.
        '--debug=FILTER2',
        # Add filters before default_filters so that the former may
        # override the latter.  I have a feeling that this "override"
        # thing could be brittle, but let's leave this here for now.
        *('--%s=%s' % pair for pair in filters),
        *('--%s=%s' % pair for pair in default_filters),
    ]
