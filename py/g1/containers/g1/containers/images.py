"""Manage images.

We make an important design decision: Importing images requires root
privilege; unlike rkt, which does not.  We make this decision for the
simplicity of implementation.  To not require root privilege, rkt has to
split import into two steps:

* The first step, the ``fetch`` command, merely copies a tar archive to
  the image repository (after optionally verifying archive's signature).
  This step does not require root privilege given that the image
  repository's directory write permission is properly configured.

* The second step, the ``prepare`` command, extracts the tar archive.
  This step requires root privilege to create files extracted from the
  tar archive that are owned by root.

In the future we might adopt rkt's design; for now, we trade security
for implementation simplicity.

Image repository layout:

* Under ``images`` there are three top-level directories: trees, tags,
  and tmp.

* ``trees`` is the directory of extracted tar archives.

* ``trees/<sha512>`` is the directory of an image, where ``sha512`` is
  the SHA512 of the tar archive.

* ``trees/<sha512>/metadata`` stores image metadata in JSON format.

* ``trees/<sha512>/rootfs`` is the root directory of image.

* ``tags`` is a directory of symlinks to images under ``trees``.

* ``tmp`` is a scratchpad for extracting the tar archive.  After the
  extraction is completed, the output is moved into the ``trees``
  directory.
"""

__all__ = [
    # Public interface.
    'ImageMetadata',
    'validate_id',
    'validate_name',
    'validate_tag',
    'validate_version',
    # Expose to apps.
    'IMAGE_LIST_STRINGIFIERS',
    'cmd_build_image',
    'cmd_cleanup',
    'cmd_import',
    'cmd_init',
    'cmd_list',
    'cmd_remove',
    'cmd_remove_tag',
    'cmd_tag',
    'make_select_image_kwargs',
    # Expose to builders, pods, and xars.
    'add_ref',
    'build_image',
    'find_id',
    'find_name_and_version',
    'get_image_dir_path',
    'get_rootfs_path',
    'get_trees_path',
    'read_metadata',
    'select_image_arguments',
    'touch',
]

import contextlib
import dataclasses
import datetime
import gzip
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from g1 import scripts
from g1.bases import argparses
from g1.bases import datetimes
from g1.bases import functionals
from g1.bases.assertions import ASSERT

from . import bases

LOG = logging.getLogger(__name__)

#
# Data type.
#


@dataclasses.dataclass(frozen=True)
class ImageMetadata:

    name: str
    version: str

    def __post_init__(self):
        validate_name(self.name)
        validate_version(self.version)


# SHA-256.
_ID_PATTERN = re.compile(r'[0-9a-f]{64}')

# For now, let's only allow a restrictive set of names.
_NAME_PATTERN = re.compile(r'[a-z0-9]+(-[a-z0-9]+)*')
_VERSION_PATTERN = re.compile(r'[a-z0-9]+((?:-|\.)[a-z0-9]+)*')


def validate_id(image_id):
    return ASSERT.predicate(image_id, _ID_PATTERN.fullmatch)


def validate_name(name):
    return ASSERT.predicate(name, _NAME_PATTERN.fullmatch)


def validate_version(version):
    return ASSERT.predicate(version, _VERSION_PATTERN.fullmatch)


def validate_tag(tag):
    return ASSERT.predicate(tag, _NAME_PATTERN.fullmatch)


#
# Top-level commands.  You need to check root privilege and acquire all
# file locks here.
#
# NOTE: When locking multiple top-level directories, lock them in
# alphabetical order to avoid deadlock.
#
# TODO: For now our locking strategy is very naive - we simply lock the
# top-level directory.  If this turns out to cause a lot of lock
# contention, we should implement a finer-grained locking strategy.
#

select_image_arguments = functionals.compose(
    argparses.begin_mutually_exclusive_group(required=True),
    argparses.argument('--id', type=validate_id, help='provide image id'),
    argparses.argument(
        '--nv',
        metavar=('NAME', 'VERSION'),
        # Sadly it looks like you can't use ``type`` with ``nargs``.
        nargs=2,
        help='provide image name and version',
    ),
    argparses.argument('--tag', type=validate_tag, help='provide image tag'),
    argparses.end,
)

image_output_arguments = functionals.compose(
    argparses.argument(
        'name',
        type=validate_name,
        help='provide output image name',
    ),
    argparses.argument(
        'version',
        type=validate_version,
        help='provide output image version',
    ),
    argparses.argument(
        'output',
        type=Path,
        help='provide output image path',
    ),
)


def make_select_image_kwargs(args):
    return {
        'image_id': args.id,
        'name': validate_name(args.nv[0]) if args.nv else None,
        'version': validate_version(args.nv[1]) if args.nv else None,
        'tag': args.tag,
    }


def cmd_init():
    """Initialize the image repository."""
    # For _extract_image.
    bases.assert_program_exist('tar')
    # For build_image.
    bases.check_program_exist('tar')
    bases.assert_root_privilege()
    bases.make_dir(_get_image_repo_path(), 0o750, bases.chown_app)
    bases.make_dir(_get_tags_path(), 0o750, bases.chown_app)
    bases.make_dir(_get_tmp_path(), 0o750, bases.chown_app)
    bases.make_dir(get_trees_path(), 0o750, bases.chown_app)


@argparses.begin_parser('build', **argparses.make_help_kwargs('build image'))
@argparses.argument(
    '--rootfs',
    type=Path,
    required=True,
    help='provide rootfs path',
)
@image_output_arguments
@argparses.end
def cmd_build_image(name, version, rootfs_path, output_path):
    # Although root privilege is not required, most likely you need it
    # to finish this.
    ASSERT.predicate(rootfs_path, Path.is_dir)
    build_image(
        ImageMetadata(name=name, version=version),
        lambda dst_path: bases.rsync_copy(rootfs_path, dst_path),
        output_path,
    )


@argparses.begin_parser(
    'import', **argparses.make_help_kwargs('import an image archive')
)
@argparses.argument('--tag', type=validate_tag, help='provide new image tag')
@argparses.argument(
    'path', type=Path, help='import image archive from this path'
)
@argparses.end
def cmd_import(image_archive_path, *, tag=None):
    """Import an image archive into the repo.

    This is a no-op if the image has been imported (i.e., an image in
    the repo has the same ID).

    For images having the same name and version, it is an error to have
    different IDs.
    """
    bases.assert_root_privilege()
    ASSERT.predicate(image_archive_path, Path.is_file)
    with _using_tmp() as tmp_path:
        image_id = _extract_image(image_archive_path, tmp_path)
        LOG.info('import image id: %s', image_id)
        _setup_image_dir(tmp_path)
        # Make sure that for every newly-imported image, its last
        # updated time is set to now; or else it could be cleaned up
        # right after import.
        _touch_image_dir(tmp_path)
        with contextlib.ExitStack() as stack:
            if tag:
                stack.enter_context(
                    bases.acquiring_exclusive(_get_tags_path())
                )
            stack.enter_context(bases.acquiring_exclusive(get_trees_path()))
            if not _maybe_import_image_dir(tmp_path, image_id):
                return
            if tag:
                image_dir_path = get_image_dir_path(image_id)
                try:
                    _tag_image(tag, image_dir_path)
                except:
                    LOG.error('cannot tag image; revert import')
                    if not _maybe_remove_image_dir(image_dir_path):
                        LOG.error('cannot revert import')
                    raise


_IMAGE_LIST_COLUMNS = frozenset((
    'id',
    'name',
    'version',
    'tags',
    'ref-count',
    'last-updated',
    'rootfs',
))
_IMAGE_LIST_DEFAULT_COLUMNS = (
    'id',
    'name',
    'version',
    'tags',
    'ref-count',
    'last-updated',
)
IMAGE_LIST_STRINGIFIERS = {
    'tags': ' '.join,
    'last-updated': datetime.datetime.isoformat,
}
ASSERT.issuperset(_IMAGE_LIST_COLUMNS, _IMAGE_LIST_DEFAULT_COLUMNS)
ASSERT.issuperset(_IMAGE_LIST_COLUMNS, IMAGE_LIST_STRINGIFIERS)


@argparses.begin_parser('list', **argparses.make_help_kwargs('list images'))
@bases.formatter_arguments(_IMAGE_LIST_COLUMNS, _IMAGE_LIST_DEFAULT_COLUMNS)
@argparses.end
def cmd_list():
    # Don't need root privilege here.
    with bases.acquiring_shared(_get_tags_path()), \
        bases.acquiring_shared(get_trees_path()):
        for image_dir_path, metadata in _iter_metadatas():
            image_id = _get_id(image_dir_path)
            last_updated = _get_last_updated(image_dir_path)
            yield {
                'id': image_id,
                'name': metadata.name,
                'version': metadata.version,
                'tags': _find_tags(image_id),
                'ref-count': _get_ref_count(image_dir_path),
                'last-updated': last_updated,
                'rootfs': get_rootfs_path(image_dir_path),
            }


@argparses.begin_parser(
    'tag', **argparses.make_help_kwargs('set tag to an image')
)
@select_image_arguments
@argparses.argument('new_tag', type=validate_tag, help='provide new image tag')
@argparses.end
def cmd_tag(*, image_id=None, name=None, version=None, tag=None, new_tag):
    bases.assert_root_privilege()
    with bases.acquiring_exclusive(_get_tags_path()):
        with bases.acquiring_shared(get_trees_path()):
            image_dir_path = ASSERT.not_none(
                _find_image_dir_path(image_id, name, version, tag)
            )
        _tag_image(new_tag, image_dir_path)


@argparses.begin_parser(
    'remove-tag', **argparses.make_help_kwargs('remove tag from an image')
)
@argparses.argument(
    'tag', type=validate_tag, help='provide image tag for removal'
)
@argparses.end
def cmd_remove_tag(tag):
    bases.assert_root_privilege()
    with bases.acquiring_exclusive(_get_tags_path()):
        try:
            _get_tag_path(tag).unlink()
        except FileNotFoundError:
            pass


@argparses.begin_parser(
    'remove',
    **argparses.make_help_kwargs('remove an image from the repository'),
)
@select_image_arguments
@argparses.end
def cmd_remove(*, image_id=None, name=None, version=None, tag=None):
    """Remove an image, or no-op if image does not exist."""
    bases.assert_root_privilege()
    with bases.acquiring_exclusive(_get_tags_path()), \
        bases.acquiring_exclusive(get_trees_path()):
        image_dir_path = _find_image_dir_path(image_id, name, version, tag)
        if image_dir_path:
            if not _maybe_remove_image_dir(image_dir_path):
                LOG.warning('image is still being used')
        else:
            LOG.debug(
                'image does not exist: image_id=%s, nv=%s:%s, tag=%s',
                image_id, name, version, tag
            )


@argparses.begin_parser(
    'cleanup', **argparses.make_help_kwargs('clean up image repository')
)
@bases.grace_period_arguments
@argparses.end
def cmd_cleanup(expiration):
    bases.assert_root_privilege()
    with bases.acquiring_exclusive(_get_tmp_path()):
        _cleanup_tmp()
    with bases.acquiring_exclusive(_get_tags_path()), \
        bases.acquiring_exclusive(get_trees_path()):
        _cleanup_trees(expiration)
        _cleanup_tags()


#
# Locking strategy.
#


@contextlib.contextmanager
def _using_tmp():
    tmp_dir_path = _get_tmp_path()
    tmp_path = None
    tmp_lock = None
    with bases.acquiring_exclusive(tmp_dir_path):
        try:
            tmp_path = Path(tempfile.mkdtemp(dir=tmp_dir_path))
            tmp_lock = bases.FileLock(tmp_path)
            tmp_lock.acquire_exclusive()
        except:
            if tmp_path:
                bases.delete_file(tmp_path)
            if tmp_lock:
                tmp_lock.release()
                tmp_lock.close()
            raise
    try:
        yield tmp_path
    finally:
        bases.delete_file(tmp_path)
        tmp_lock.release()
        tmp_lock.close()


#
# Repo layout.
#

_IMAGES = 'images'

_TAGS = 'tags'
_TREES = 'trees'
_TMP = 'tmp'

_METADATA = 'metadata'
_ROOTFS = 'rootfs'


def _get_image_repo_path():
    return bases.get_repo_path() / _IMAGES


def _get_tags_path():
    return _get_image_repo_path() / _TAGS


def get_trees_path():
    return _get_image_repo_path() / _TREES


def _get_tmp_path():
    return _get_image_repo_path() / _TMP


def get_image_dir_path(image_id):
    return get_trees_path() / validate_id(image_id)


def _get_id(image_dir_path):
    return validate_id(image_dir_path.name)


def _get_metadata_path(image_dir_path):
    return image_dir_path / _METADATA


def get_rootfs_path(image_dir_path):
    return image_dir_path / _ROOTFS


def _get_tag_path(tag):
    return _get_tags_path() / validate_tag(tag)


def _get_tag(tag_path):
    return validate_tag(tag_path.name)


def _get_tag_target(image_dir_path):
    return Path('..') / _TREES / _get_id(image_dir_path)


#
# Functions below require caller acquiring locks.
#

#
# Top-level directories.
#


def _cleanup_tmp():
    for tmp_path in _get_tmp_path().iterdir():
        if not tmp_path.is_dir():
            LOG.info('remove unknown temporary file: %s', tmp_path)
            tmp_path.unlink()
            continue
        tmp_lock = bases.try_acquire_exclusive(tmp_path)
        if not tmp_lock:
            continue
        try:
            LOG.info('remove temporary directory: %s', tmp_path)
            shutil.rmtree(tmp_path)
        finally:
            tmp_lock.release()
            tmp_lock.close()


def _cleanup_trees(expiration):
    LOG.info('remove images before: %s', expiration)
    for image_dir_path in get_trees_path().iterdir():
        if image_dir_path.is_dir():
            if _get_last_updated(image_dir_path) < expiration:
                _maybe_remove_image_dir(image_dir_path)
        else:
            LOG.info('remove unknown file under trees: %s', image_dir_path)
            image_dir_path.unlink()


def _cleanup_tags():
    for tag_path in _get_tags_path().iterdir():
        if tag_path.is_symlink():
            if not tag_path.resolve().exists():
                LOG.info('remove dangling tag: %s', tag_path)
                tag_path.unlink()
        else:
            LOG.info('remove unknown file under tags: %s', tag_path)
            bases.delete_file(tag_path)


#
# Image builder.
#


def build_image(metadata, make_rootfs, output_path):
    ASSERT.not_predicate(output_path, bases.lexists)
    with tempfile.TemporaryDirectory(
        dir=output_path.parent,
        prefix=output_path.name + '-',
    ) as temp_output_dir_path:
        temp_output_dir_path = Path(temp_output_dir_path)
        _write_metadata(metadata, temp_output_dir_path)
        make_rootfs(get_rootfs_path(temp_output_dir_path))
        _setup_image_dir(temp_output_dir_path)
        scripts.run([
            'tar',
            '--create',
            *('--file', output_path),
            '--gzip',
            *('--directory', temp_output_dir_path),
            _METADATA,
            _ROOTFS,
        ])


#
# Image extraction.
#


def _extract_image(archive_path, dst_dir_path):
    # We assume archive is always gzip-compressed for now.
    hasher = hashlib.sha256()
    # If we are running as root, we can and should preserve the
    # original owners and permissions.
    i_am_root = bases.PARAMS.use_root_privilege.get()
    # TODO: Should we use stdlib's tarfile rather than calling tar?
    with scripts.using_stdin(subprocess.PIPE), scripts.popen([
        'tar',
        '--extract',
        *('--file', '-'),
        *('--directory', dst_dir_path),
        *(('--same-owner', '--same-permissions') if i_am_root else ()),
    ]) as proc:
        try:
            with gzip.open(archive_path, 'rb') as archive:
                while True:
                    data = archive.read(4096)
                    if not data:
                        break
                    proc.stdin.write(data)
                    hasher.update(data)
        except:
            proc.kill()
            raise
        else:
            proc.stdin.close()
            proc.wait()
            ASSERT.equal(proc.poll(), 0)
    return hasher.hexdigest()


def _setup_image_dir(image_dir_path):
    bases.setup_file(image_dir_path, 0o750, bases.chown_app)
    bases.setup_file(
        _get_metadata_path(image_dir_path), 0o640, bases.chown_app
    )
    bases.setup_file(get_rootfs_path(image_dir_path), 0o755, bases.chown_root)


#
# Image directories.
#


def _maybe_import_image_dir(src_path, image_id):
    image_dir_path = get_image_dir_path(image_id)
    if image_dir_path.exists():
        LOG.warning('not import duplicated image: %s', image_id)
        return False
    else:
        _assert_unique_name_and_version(read_metadata(src_path))
        src_path.rename(image_dir_path)
        return True


def _assert_unique_name_and_version(new_metadata):
    for image_dir_path, metadata in _iter_metadatas():
        ASSERT(
            new_metadata.name != metadata.name
            or new_metadata.version != metadata.version,
            'expect unique image name and version: {}, {}',
            image_dir_path,
            new_metadata,
        )


def _iter_image_dir_paths():
    for image_dir_path in get_trees_path().iterdir():
        if not image_dir_path.is_dir():
            LOG.debug('encounter unknown file under trees: %s', image_dir_path)
        else:
            yield image_dir_path


def _find_image_dir_path(image_id, name, version, tag):
    """Return path to image directory or None if not found."""
    ASSERT.only_one((image_id, name or version, tag))
    ASSERT.not_xor(name, version)
    if name:
        # We check duplicated image name and version when images are
        # imported, and so we do not check it again here.
        for image_dir_path in _iter_image_dir_paths():
            metadata = read_metadata(image_dir_path)
            if metadata.name == name and metadata.version == version:
                return image_dir_path
        return None
    if image_id:
        image_dir_path = get_image_dir_path(image_id)
    else:
        tag_path = _get_tag_path(tag)
        if not bases.lexists(tag_path):
            return None
        image_dir_path = _get_image_dir_path_from_tag(tag_path)
    return image_dir_path if image_dir_path.is_dir() else None


def find_id(*, name=None, version=None, tag=None):
    image_dir_path = _find_image_dir_path(None, name, version, tag)
    return _get_id(image_dir_path) if image_dir_path else None


def find_name_and_version(*, image_id=None, tag=None):
    image_dir_path = _find_image_dir_path(image_id, None, None, tag)
    if image_dir_path is None:
        return None, None
    else:
        metadata = read_metadata(image_dir_path)
        return metadata.name, metadata.version


def _maybe_remove_image_dir(image_dir_path):
    if _get_ref_count(image_dir_path) <= 1:
        LOG.info('remove image directory: %s', image_dir_path)
        for tag_path in _find_tag_paths(image_dir_path):
            tag_path.unlink()
        if image_dir_path.exists():
            shutil.rmtree(image_dir_path)
        return True
    else:
        LOG.debug('not remove image directory: %s', image_dir_path)
        return False


#
# Metadata.
#


def _iter_metadatas():
    """Iterate over metadata of every image."""
    for image_dir_path in _iter_image_dir_paths():
        yield image_dir_path, read_metadata(image_dir_path)


def read_metadata(image_dir_path):
    """Read image metadata from an image directory."""
    return bases.read_jsonobject(
        ImageMetadata, _get_metadata_path(image_dir_path)
    )


def _write_metadata(metadata, image_dir_path):
    bases.write_jsonobject(metadata, _get_metadata_path(image_dir_path))


def add_ref(image_id, dst_path):
    os.link(
        ASSERT.predicate(
            _get_metadata_path(get_image_dir_path(image_id)), Path.is_file
        ),
        dst_path,
    )


def _get_ref_count(image_dir_path):
    try:
        return _get_metadata_path(image_dir_path).stat().st_nlink
    except FileNotFoundError:
        return 0


def touch(image_id):
    _touch_image_dir(get_image_dir_path(image_id))


def _touch_image_dir(image_dir_path):
    ASSERT.predicate(_get_metadata_path(image_dir_path), Path.is_file).touch()


def _get_last_updated(image_dir_path):
    return datetimes.utcfromtimestamp(
        _get_metadata_path(image_dir_path).stat().st_mtime
    )


#
# Tags.
#


def _get_image_dir_path_from_tag(tag_path):
    return ASSERT.predicate(tag_path, Path.is_symlink).resolve()


def _find_tags(image_id):
    return sorted(map(_get_tag, _find_tag_paths(get_image_dir_path(image_id))))


def _find_tag_paths(image_dir_path):
    for tag_path in _get_tags_path().iterdir():
        if not tag_path.is_symlink():
            LOG.debug('encounter unknown file under tags: %s', tag_path)
        elif tag_path.resolve().name == image_dir_path.name:
            yield tag_path


def _tag_image(tag, image_dir_path):
    tag_path = _get_tag_path(tag)
    # ".tmp" is not a validate tag, and so it will not conflict.
    new_tag_path = tag_path.with_suffix('.tmp')
    new_tag_path.symlink_to(_get_tag_target(image_dir_path))
    new_tag_path.replace(tag_path)
