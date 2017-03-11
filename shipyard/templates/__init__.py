"""Language-agnostic build rules."""

__all__ = [
    'define_archive',
    'define_package_common',
]

from pathlib import Path
import collections
import logging

import foreman

from garage import scripts


LOG = logging.getLogger(__name__)


# Info of an archive (basically a URI to a tarball)
ArchiveInfo = collections.namedtuple('ArchiveInfo', [
    'uri',       # URI to the archive
    'filename',  # Local filename for the downloaded archive
    'output',    # Local directory name of the extracted contents
])


def define_archive(name, *, uri, filename, output, derive_dst_path,
                   wget_headers=()):
    """Define an archive, including:
       * NAME/archive_info and NAME/archive_destination parameter
       * NAME/download rule
    """

    (foreman.define_parameter('%s/archive_info' % name)
     .with_doc('Archive info.')
     .with_type(ArchiveInfo)
     .with_parse(lambda info: ArchiveInfo(*info.split(',')))
     .with_default(ArchiveInfo(uri=uri, filename=filename, output=output)))

    (foreman.define_parameter('%s/archive_destination' % name)
     .with_doc('Local path for extracting archive into.')
     .with_type(Path)
     .with_derive(derive_dst_path))

    @foreman.rule('%s/download' % name)
    def download(parameters):
        """Download and extract archive."""

        archive_info = parameters['%s/archive_info' % name]

        destination = parameters['%s/archive_destination' % name]
        scripts.mkdir(destination)

        archive_path = destination / archive_info.filename
        if archive_path.exists():
            LOG.info('skip downloading archive: %s', archive_info.uri)
        else:
            LOG.info('download archive: %s', archive_info.uri)
            scripts.wget(archive_info.uri, archive_path, headers=wget_headers)
        # Just a sanity check
        scripts.ensure_file(archive_path)

        output_path = destination / archive_info.output
        if output_path.exists():
            LOG.info('skip extracting archive: %s', archive_path)
        else:
            LOG.info('extract archive: %s', archive_path)
            if archive_path.suffix == '.zip':
                scripts.unzip(archive_path, destination)
            else:
                scripts.tar_extract(archive_path, destination)
        # Just a sanity check
        scripts.ensure_directory(output_path)

    return download


def define_package_common(name, *, derive_src_path, derive_drydock_src_path):
    """Define common parts of a (first-party) package, including src and
       drydock_src parameter.  This is most likely to be useful to other
       rule templates, not to your build rules.
    """

    (foreman.define_parameter('%s/src' % name)
     .with_doc('Path to the package source code.')
     .with_type(Path)
     .with_derive(derive_src_path))

    (foreman.define_parameter('%s/drydock_src' % name)
     .with_doc('Path to the copy of source code to be built from.')
     .with_type(Path)
     .with_derive(derive_drydock_src_path))
