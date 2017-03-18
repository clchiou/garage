"""Language-agnostic build rules."""

__all__ = [
    'define_archive',
    'define_copy_src',
    'define_distro_packages',
    'define_git_repo',
]

from collections import namedtuple
import logging

from foreman import define_parameter, get_relpath, rule

from garage import scripts

from . import utils


LOG = logging.getLogger(__name__)


# Info of an archive (basically a URI to a tarball)
ArchiveInfo = namedtuple('ArchiveInfo', [
    'uri',       # URI to the archive
    'filename',  # Local filename for the downloaded archive
    'output',    # Local directory name of the extracted contents
    'checksum',  # Archive file checksum
])


ArchiveRules = namedtuple('ArchiveRules', 'download')


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

    return ArchiveRules(download=download)


CopySrcRules = namedtuple('CopySrcRules', 'copy_src')


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
def define_copy_src(*, root: 'root', name: 'name'):
    """Define [NAME/]copy_src rule.

       This is most likely to be useful to other rule templates, not to
       your build rules.
    """

    relpath = get_relpath()

    @rule(name + 'copy_src')
    def copy_src(parameters):
        """Copy src into drydock_src (and then you will build from there)."""
        src = parameters[root] / relpath
        drydock_src = parameters['//base:drydock'] / relpath
        LOG.info('copy source: %s -> %s', src, drydock_src)
        scripts.mkdir(drydock_src)
        srcs = ['%s/' % src]  # Appending '/' to src is an rsync trick
        scripts.rsync(srcs, drydock_src, delete=True, excludes=EXCLUDES)

    return CopySrcRules(copy_src=copy_src)


DistroPackagesRules = namedtuple('DistroPackagesRules', 'install_packages')


@utils.parse_common_args
def define_distro_packages(packages, *, name: 'name'):
    """Define [NAME/]install_packages."""

    (define_parameter
     .list_typed(name + 'distro_packages')
     .with_default(packages))

    @rule(name + 'install_packages')
    def install_packages(parameters):
        """Install deb packages."""
        with scripts.using_sudo():
            scripts.apt_get_install(parameters[name + 'distro_packages'])

    return DistroPackagesRules(install_packages=install_packages)


GitRepoInfo = namedtuple('GitRepoInfo', 'repo treeish')


GitRepoRules = namedtuple('GitRepoRules', 'git_clone')


@utils.parse_common_args
def define_git_repo(*, name: 'name',
                    repo, treeish=None):
    """Define [NAME/]git_clone rule."""

    (define_parameter.namedtuple_typed(GitRepoInfo, name + 'git_repo')
     .with_default(GitRepoInfo(repo=repo, treeish=treeish)))

    relpath = get_relpath()

    @rule(name + 'git_clone')
    def git_clone(parameters):
        """Clone and checkout git repo."""
        drydock_src = parameters['//base:drydock'] / relpath
        if not drydock_src.exists():
            LOG.info('clone into: %s', drydock_src)
            git_repo = parameters[name + 'git_repo']
            scripts.git_clone(
                repo=git_repo.repo,
                local_path=drydock_src,
                checkout=git_repo.treeish,
            )

    return GitRepoRules(git_clone=git_clone)
