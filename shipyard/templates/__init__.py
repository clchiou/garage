"""Language-agnostic build rules."""

__all__ = [
    'define_archive',
    'define_package_common',
    # Helper function for writing templates
    'parse_common_args',
    'tapeout_files',
    'tapeout_libraries',
]

from pathlib import Path
import collections
import functools
import logging

import foreman

from garage import scripts


LOG = logging.getLogger(__name__)


def parse_common_args(template):
    """Parse template arguments by the convention."""

    # Don't use setdefault() in parsers since arguments may be
    # None-valued.

    def parse_root(kwargs, arg):
        root = kwargs.get(arg)
        kwargs[arg] = root or '//base:root'

    def parse_name(kwargs, arg):
        name = kwargs.get(arg)
        if not name:
            name = ''
        elif not name.endswith('/'):
            name += '/'
        kwargs[arg] = name

    parsers = []
    for arg, anno in template.__annotations__.items():
        if anno == 'root':
            parsers.append(functools.partial(parse_root, arg=arg))
        elif anno == 'name':
            parsers.append(functools.partial(parse_name, arg=arg))
        else:
            raise AssertionError('cannot parse: %s' % anno)

    @functools.wraps(template)
    def wrapper(*args, **kwargs):
        for parser in parsers:
            parser(kwargs)
        return template(*args, **kwargs)

    return wrapper


# Info of an archive (basically a URI to a tarball)
ArchiveInfo = collections.namedtuple('ArchiveInfo', [
    'uri',       # URI to the archive
    'filename',  # Local filename for the downloaded archive
    'output',    # Local directory name of the extracted contents
])


@parse_common_args
def define_archive(*, name: 'name',
                   uri, filename, output,
                   wget_headers=()):
    """Define an archive, including:
       * [NAME/]archive_info parameter
       * [NAME/]download rule
    """

    relpath = foreman.get_relpath()

    (foreman.define_parameter(name + 'archive_info')
     .with_doc('Archive info.')
     .with_type(ArchiveInfo)
     .with_parse(lambda info: ArchiveInfo(*info.split(',')))
     .with_default(ArchiveInfo(uri=uri, filename=filename, output=output)))

    @foreman.rule(name + 'download')
    def download(parameters):
        """Download and extract archive."""

        archive_info = parameters[name + 'archive_info']

        drydock_src = parameters['//base:drydock'] / relpath
        scripts.mkdir(drydock_src)

        archive_path = drydock_src / archive_info.filename
        if not archive_path.exists():
            LOG.info('download archive: %s', archive_info.uri)
            scripts.wget(archive_info.uri, archive_path, headers=wget_headers)
        # Just a sanity check
        scripts.ensure_file(archive_path)

        output_path = drydock_src / archive_info.output
        if not output_path.exists():
            LOG.info('extract archive: %s', archive_path)
            if archive_path.suffix == '.zip':
                scripts.unzip(archive_path, drydock_src)
            else:
                scripts.tar_extract(archive_path, drydock_src)
        # Just a sanity check
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


@parse_common_args
def define_package_common(*, root: 'root', name: 'name'):
    """Define common parts of a (first-party) package, including:
       * [NAME/]src and [NAME/]drydock_src parameter
       * [NAME/]copy_src rule

       This is most likely to be useful to other rule templates, not to
       your build rules.
    """

    relpath = foreman.get_relpath()

    (foreman.define_parameter(name + 'src')
     .with_doc('Path to the package source code.')
     .with_type(Path)
     .with_derive(lambda ps: ps[root] / relpath))

    @foreman.rule(name + 'copy_src')
    def copy_src(parameters):
        """Copy src into drydock_src (and then you will build from there)."""
        src = parameters[name + 'src']
        drydock_src = parameters['//base:drydock'] / relpath
        LOG.info('copy source: %s -> %s', src, drydock_src)
        scripts.mkdir(drydock_src)
        srcs = ['%s/' % src]  # Appending '/' to src is an rsync trick
        scripts.rsync(srcs, drydock_src, delete=True, excludes=EXCLUDES)

    return copy_src


def tapeout_files(parameters, paths):
    with scripts.using_sudo():
        rootfs = parameters['//base:drydock/rootfs']
        scripts.rsync(paths, rootfs, relative=True)


def tapeout_libraries(parameters, lib_dir, libnames):
    lib_dir = Path(lib_dir)
    libs = []
    for libname in libnames:
        libs.extend(lib_dir.glob('%s*' % libname))
    tapeout_files(parameters, libs)
