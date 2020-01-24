__all__ = [
    'ArchiveTypes',
    'Compressors',
    'assert_command_exist',
    'check_command_exist',
    'export_path',
    'get_url_path',
    'guess_archive_type',
    'guess_compressor',
    'remove_archive_suffix',
]

import enum
import logging
import os
import shutil
import urllib.parse
from pathlib import Path

from g1.bases.assertions import ASSERT

from . import bases

LOG = logging.getLogger(__name__)


class ArchiveTypes(enum.Enum):
    UNKNOWN = enum.auto()
    TAR = enum.auto()
    ZIP = enum.auto()


class Compressors(enum.Enum):
    UNKNOWN = enum.auto()
    UNCOMPRESSED = enum.auto()
    BZIP2 = enum.auto()
    GZIP = enum.auto()
    XZ = enum.auto()
    ZIP = enum.auto()


def assert_command_exist(command):
    ASSERT.predicate(command, shutil.which, message='expect command exist: {}')


def check_command_exist(command):
    if not shutil.which(command):
        LOG.warning(
            'command %s does not exist; some features are unavailable', command
        )


def export_path(var, path):
    """Prepend path to a PATH-like environment variable."""
    paths = os.environ.get(var)
    paths = '%s:%s' % (path, paths) if paths else str(path)
    LOG.info('prepend %s: %r', var, paths)
    if not bases.get_dry_run():
        os.environ[var] = paths


def get_url_path(url):
    return Path(urllib.parse.urlparse(url).path)


_SUFFIXES = (
    ('.tar', ArchiveTypes.TAR, Compressors.UNCOMPRESSED),
    ('.tar.bz2', ArchiveTypes.TAR, Compressors.BZIP2),
    ('.tbz2', ArchiveTypes.TAR, Compressors.BZIP2),
    ('.tar.gz', ArchiveTypes.TAR, Compressors.GZIP),
    ('.tgz', ArchiveTypes.TAR, Compressors.GZIP),
    ('.tar.xz', ArchiveTypes.TAR, Compressors.XZ),
    ('.txz', ArchiveTypes.TAR, Compressors.XZ),
    ('.zip', ArchiveTypes.ZIP, Compressors.ZIP),
    # Put non-archive suffixes last as they overlaps suffixes above.
    ('.bz2', ArchiveTypes.UNKNOWN, Compressors.BZIP2),
    ('.gz', ArchiveTypes.UNKNOWN, Compressors.GZIP),
    ('.xz', ArchiveTypes.UNKNOWN, Compressors.XZ),
)


def guess_archive_type(filename):
    return _guess(filename)[0]


def guess_compressor(filename):
    return _guess(filename)[1]


def _guess(filename):
    for suffix, archive_type, compressor in _SUFFIXES:
        if filename.endswith(suffix):
            return archive_type, compressor
    return ArchiveTypes.UNKNOWN, Compressors.UNKNOWN


def remove_archive_suffix(filename):
    for suffix, archive_type, _ in _SUFFIXES:
        if (
            archive_type is not ArchiveTypes.UNKNOWN
            and filename.endswith(suffix)
        ):
            return filename[:-len(suffix)]
    return filename
