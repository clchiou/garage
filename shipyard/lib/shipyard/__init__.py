"""Generic helper functions."""

__all__ = [
    # Generic scripting helpers.
    'insert_path',
    'copy_source',
    'ensure_file',
    'ensure_directory',
    'execute',
    'git_clone',
    'rsync',
    'run_commands',
    'tar_create',
    'tar_extract',
    'wget',
    # OS Package helpers.
    'install_packages',
    # build.py templates.
    'define_archive',
    'define_package_common',
    # Helpers for the build image/pod phases.
    'build_appc_image',
    'tapeout_files',
    'tapeout_libraries',
    'write_json',
    # More helpers.
    'combine_dicts',
]

import hashlib
import itertools
import json
import logging
import os
from collections import namedtuple
from contextlib import ExitStack
from pathlib import Path
from subprocess import PIPE, Popen, check_call, check_output

from foreman import (
    decorate_rule,
    define_parameter,
    to_path,
)


LOG = logging.getLogger(__name__)


### Generic scripting helpers.


def insert_path(path_element):
    """Prepend path element to PATH environment variable."""
    path = os.environ.get('PATH')
    path = '%s:%s' % (path_element, path) if path else str(path_element)
    LOG.info('new PATH: %s', path)
    os.environ['PATH'] = path


def copy_source(src, build_src):
    """Copy src into build_src (and then you will build from there)."""
    LOG.info('copy source: %s -> %s', src, build_src)
    ensure_directory(build_src)
    # NOTE: Appending slash to src is an rsync trick.
    rsync(['%s/' % src], build_src, delete=True, excludes=[
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
    ])


def ensure_file(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError('not a file: %s' % path)


def ensure_directory(path, mode=0o777):
    """Return True when the directory exists; else return false and
       create the directory.
    """
    # exist_ok is added to Path.mkdir until Python 3.5 :(
    path = Path(path)
    if path.exists():
        if not path.is_dir():
            raise FileExistsError('not a directory: %s' % path)
        return True
    LOG.debug('make directory: %s', path)
    path.mkdir(mode=mode, parents=True)
    return False


def execute(args, *, return_output=False, cwd=None):
    """Log and then call subprocess.check_call."""
    args = list(map(str, args))
    if LOG.isEnabledFor(logging.DEBUG):
        LOG.debug('execute: %s # cwd = %r', ' '.join(args), cwd)
    if return_output:
        caller = check_output
    else:
        caller = check_call
    cwd = str(cwd) if cwd else None
    return caller(args, cwd=cwd)


def git_clone(repo, local_path=None, checkout=None):
    if local_path and local_path.exists():
        if not local_path.is_dir():
            raise FileExistsError('not a directory: %s' % local_path)
    else:
        cmd = ['git', 'clone', repo]
        if local_path:
            cmd.append(local_path.name)
        LOG.info('clone git repo %s', repo)
        cwd = local_path.parent if local_path else None
        execute(cmd, cwd=cwd)
    if checkout:
        LOG.info('checkout %s %s', repo, checkout)
        cwd = local_path if local_path else None
        execute(['git', 'checkout', checkout], cwd=cwd)


def run_commands(commands_str, path=None):
    for command in commands_str.split('\n'):
        command = command.strip().split()
        if command:
            execute(command, cwd=path)


def rsync(srcs, dst, *,
          delete=False,
          relative=False,
          includes=(), excludes=(),
          sudo=False):
    if not srcs:
        LOG.warning('rsync: empty srcs: %r', srcs)
        return
    cmd = ['rsync', '--archive']
    if sudo:
        cmd.insert(0, 'sudo')
    if delete:
        cmd.append('--delete')
    if relative:
        cmd.append('--relative')
    for include in includes:
        cmd.extend(['--include', include])
    for exclude in excludes:
        cmd.extend(['--exclude', exclude])
    cmd.extend(srcs)
    cmd.append(dst)
    execute(cmd)


def tar_create(src_dir, srcs, tarball_path, *, sudo=False, tar_extra_flags=()):
    """Create a tarball."""
    src_dir = Path(src_dir)
    cmd = [
        'tar',
        '--create',
        '--file', Path(tarball_path).absolute(),
        '--directory', src_dir,
    ]
    cmd.extend(tar_extra_flags)
    if sudo:
        cmd.insert(0, 'sudo')
    for src in srcs:
        src = Path(src)
        if src.is_absolute():
            src = src.relative_to(src_dir)
        cmd.append(src)
    LOG.info('create %s', tarball_path)
    execute(cmd)


def tar_extract(tarball_path, output_path=None):
    """Extract a tarball."""
    tarball_path = Path(tarball_path)
    name = tarball_path.name
    if name.endswith('.tar'):
        compress_flag = None
    elif name.endswith('.tar.bz2'):
        compress_flag = '--bzip2'
    elif name.endswith('.tar.gz') or name.endswith('.tgz'):
        compress_flag = '--gzip'
    elif name.endswith('.tar.xz'):
        compress_flag = '--xz'
    else:
        raise RuntimeError('cannot parse tarball suffix: %s' % tarball_path)
    cmd = ['tar', '--extract', '--file', tarball_path]
    if compress_flag:
        cmd.append(compress_flag)
    if output_path:
        cmd.extend(['--directory', output_path])
    LOG.info('extract %s', tarball_path)
    execute(cmd)


def wget(uri, output_path=None, *, headers=()):
    cmd = ['wget', uri]
    if output_path:
        cmd.extend(['--output-document', output_path])
    for header in headers:
        cmd.extend(['--header', header])
    LOG.info('download %s', uri)
    execute(cmd)


### OS Package helpers.


def install_packages(pkgs):
    if LOG.isEnabledFor(logging.INFO):
        LOG.info('install %s', ' '.join(pkgs))
    cmd = ['sudo', 'apt-get', 'install', '--yes']
    cmd.extend(pkgs)
    execute(cmd)


### build.py templates.


ArchiveInfo = namedtuple('ArchiveInfo', 'uri filename output')


def define_archive(
        *,
        uri, filename, output,
        derive_dst_path,
        wget_headers=()):

    (
        define_parameter('archive_info')
        .with_doc("""Archive info.""")
        .with_type(ArchiveInfo)
        .with_parse(lambda info: ArchiveInfo(*info.split(',')))
        .with_default(ArchiveInfo(uri=uri, filename=filename, output=output))
    )

    (
        define_parameter('archive_destination')
        .with_doc("""Location of archive.""")
        .with_type(Path)
        .with_derive(derive_dst_path)
    )

    @decorate_rule
    def download(parameters):
        """Download and extract archive."""

        destination = parameters['archive_destination']

        ensure_directory(destination)
        archive_info = parameters['archive_info']

        archive_path = destination / archive_info.filename
        if not archive_path.exists():
            LOG.info('download archive: %s', archive_info.uri)
            wget(archive_info.uri, archive_path, headers=wget_headers)
        ensure_file(archive_path)

        output_path = destination / archive_info.output
        if not output_path.exists():
            LOG.info('extract archive: %s', archive_path)
            if archive_path.suffix == '.zip':
                execute(['unzip', archive_path], cwd=destination)
            else:
                tar_extract(archive_path, destination)
        ensure_directory(output_path)

    return download


def define_package_common(
        *,
        derive_src_path,
        derive_build_src_path):
    (
        define_parameter('src')
        .with_doc("""Location of the source.""")
        .with_type(Path)
        .with_derive(derive_src_path)
    )
    (
        define_parameter('build_src')
        .with_doc("""Location of the copied source to build from.""")
        .with_type(Path)
        .with_derive(derive_build_src_path)
    )


### Helpers for the build image phase.


# TODO: Encrypt and/or sign the image.
def build_appc_image(src_dir, dst_dir):
    LOG.info('build appc image: %s -> %s', src_dir, dst_dir)

    for target in ('manifest', 'rootfs'):
        target = src_dir / target
        if not target.exists():
            raise FileNotFoundError(str(target))

    ensure_directory(dst_dir)

    with ExitStack() as stack:
        proc_tar = stack.enter_context(Popen(
            ['tar', '--create', 'manifest', 'rootfs'],
            stdout=PIPE,
            cwd=str(src_dir),
        ))

        proc_gzip = stack.enter_context(Popen(
            ['gzip'],
            stdin=PIPE,
            stdout=stack.enter_context((dst_dir / 'image.aci').open('wb')),
        ))

        sha512 = hashlib.sha512()
        while True:
            data = proc_tar.stdout.read(4096)
            if not data:
                break
            sha512.update(data)
            proc_gzip.stdin.write(data)

        proc_tar.stdout.close()
        proc_gzip.stdin.close()

        (dst_dir / 'sha512').write_text('%s\n' % sha512.hexdigest())

        retcode = proc_tar.wait()
        if retcode != 0:
            raise RuntimeError('error in tar: rc=%d' % retcode)

        retcode = proc_gzip.wait()
        if retcode != 0:
            raise RuntimeError('error in gzip: rc=%d' % retcode)


def tapeout_files(parameters, paths):
    rsync(paths, parameters['//base:rootfs'], relative=True, sudo=True)


def tapeout_libraries(parameters, lib_dir, libnames):
    lib_dir = Path(lib_dir)
    libs = list(itertools.chain.from_iterable(
        lib_dir.glob('%s*' % name) for name in libnames))
    tapeout_files(parameters, libs)


def write_json(json_object, output_path):
    with output_path.open('w') as output_file:
        output_file.write(json.dumps(json_object, indent=4, sort_keys=True))
        output_file.write('\n')


### More helpers.


def combine_dicts(*member_dicts, exclude_keys=()):
    combined_dict = {}
    for member_dict in member_dicts:
        combined_dict.update(member_dict)
    for key in exclude_keys:
        combined_dict.pop(key, None)
    return combined_dict
