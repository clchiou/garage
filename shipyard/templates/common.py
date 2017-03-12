"""Language-agnostic build rules."""

__all__ = [
    'define_archive',
    'define_package_common',
]

import collections
import logging

from foreman import define_parameter, get_relpath, rule

from garage import scripts

from . import utils


LOG = logging.getLogger(__name__)


# Info of an archive (basically a URI to a tarball)
ArchiveInfo = collections.namedtuple('ArchiveInfo', [
    'uri',       # URI to the archive
    'filename',  # Local filename for the downloaded archive
    'output',    # Local directory name of the extracted contents
    'checksum',  # Archive file checksum
])


@utils.parse_common_args
def define_archive(*, name: 'name',
                   uri, filename, output,
                   checksum=None,
                   wget_headers=()):
    """Define an archive, including:
       * [NAME/]archive_info parameter
       * [NAME/]download rule
    """

    relpath = get_relpath()

    (define_parameter.namedtuple_typed(ArchiveInfo, name + 'archive_info')
     .with_doc('Archive info.')
     .with_default(ArchiveInfo(
         uri=uri, filename=filename, output=output, checksum=checksum)))

    @rule(name + 'download')
    def download(parameters):
        """Download and extract archive."""

        archive_info = parameters[name + 'archive_info']

        drydock_src = parameters['//base:drydock'] / relpath
        scripts.mkdir(drydock_src)

        archive_path = drydock_src / archive_info.filename
        if not archive_path.exists():
            LOG.info('download archive: %s', archive_info.uri)
            scripts.wget(archive_info.uri, archive_path, headers=wget_headers)
            scripts.ensure_file(archive_path)
            if archive_info.checksum:
                scripts.ensure_checksum(archive_path, archive_info.checksum)

        output_path = drydock_src / archive_info.output
        if not output_path.exists():
            LOG.info('extract archive: %s', archive_path)
            if archive_path.suffix == '.zip':
                scripts.unzip(archive_path, drydock_src)
            else:
                scripts.tar_extract(archive_path, drydock_src)
            scripts.ensure_directory(output_path)

    return download


EXCLUDES = [
    '*.egg-info',
    '*.pyc',
    '.idea',
    '.git',
    '.gradle',
    '.hg',
    '.svn',
    '__pycache__',
    'build',
    'dist',
    'gradle',
    'gradlew',
    'gradlew.bat',
    'node_modules',
]


@utils.parse_common_args
def define_package_common(*, root: 'root', name: 'name'):
    """Define common parts of a (first-party) package, including:
       * [NAME/]src and [NAME/]drydock_src parameter
       * [NAME/]copy_src rule

       This is most likely to be useful to other rule templates, not to
       your build rules.
    """

    relpath = get_relpath()

    (define_parameter.path_typed(name + 'src')
     .with_doc('Path to the package source code.')
     .with_derive(lambda ps: ps[root] / relpath))

    @rule(name + 'copy_src')
    def copy_src(parameters):
        """Copy src into drydock_src (and then you will build from there)."""
        src = parameters[name + 'src']
        drydock_src = parameters['//base:drydock'] / relpath
        LOG.info('copy source: %s -> %s', src, drydock_src)
        scripts.mkdir(drydock_src)
        srcs = ['%s/' % src]  # Appending '/' to src is an rsync trick
        scripts.rsync(srcs, drydock_src, delete=True, excludes=EXCLUDES)

    return copy_src
