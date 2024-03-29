"""Wrappers of frequently-used commands."""

__all__ = [
    'chown',
    'cp',
    'ln',
    'make_relative_symlink',
    'mkdir',
    'rm',
    'rmdir',
    'validate_checksum',
    'which',
    'write_bytes',
    # Archive.
    'extract',
    'tar_extract',
    'unzip',
    # Build.
    'make',
    # Distro.
    'apt_get_clean',
    'apt_get_full_upgrade',
    'apt_get_install',
    'apt_get_update',
    # Network.
    'wget',
    # Source repos.
    'git_clone',
]

import os
import os.path
import subprocess
from pathlib import Path

from g1.bases.assertions import ASSERT

from . import bases
from . import utils


def chown(owner, group, path):
    bases.run([
        'chown',
        owner if group is None else '%s:%s' % (owner, group),
        path,
    ])


def cp(src, dst, *, recursive=False, preserve=()):
    bases.run([
        'cp',
        '--force',
        *(('--recursive', ) if recursive else ()),
        *(('--preserve=%s' % ','.join(preserve), ) if preserve else ()),
        src,
        dst,
    ])


def make_relative_symlink(target_path, link_path):
    # TODO: We require both paths being absolute for now as I am not
    # sure whether os.path.relpath will work correctly.
    target_path = ASSERT.predicate(Path(target_path), Path.is_absolute)
    link_path = ASSERT.predicate(Path(link_path), Path.is_absolute)
    # Use os.path.relpath because Path.relative_to cannot derive this
    # type of relative path.
    target_relpath = os.path.relpath(target_path, link_path.parent)
    mkdir(link_path.parent)
    with bases.using_cwd(link_path.parent):
        ln(target_relpath, link_path.name)


def ln(target, link_name):
    bases.run(['ln', '--symbolic', target, link_name])


def mkdir(path):
    bases.run(['mkdir', '--parents', path])


def rm(path, *, recursive=False):
    bases.run([
        'rm',
        '--force',
        *(('--recursive', ) if recursive else ()),
        path,
    ])


def rmdir(path, *, parents=False, ignore_fail_on_non_empty=False):
    bases.run([
        'rmdir',
        *(('--parents', ) if parents else ()),
        *(('--ignore-fail-on-non-empty', ) if ignore_fail_on_non_empty else
          ()),
        path,
    ])


def validate_checksum(path, checksum):
    command, checksum = _parse_checksum(checksum)
    command_input = ('%s %s' % (checksum, path)).encode('utf-8')
    with bases.doing_check(False):
        with bases.using_input(command_input):
            proc = bases.run([command, '--check', '--status', '-'])
            return proc.returncode == 0


def _parse_checksum(checksum):
    for prefix, command in (
        ('md5:', 'md5sum'),
        ('sha256:', 'sha256sum'),
        ('sha512:', 'sha512sum'),
    ):
        if checksum.startswith(prefix):
            return command, checksum[len(prefix):]
    return ASSERT.unreachable('unknown checksum algorithm: {}', checksum)


def which(name):
    with bases.doing_capture_stdout():
        return Path(bases.run(['which', name]).stdout.decode('utf-8').strip())


def write_bytes(data, path):
    with bases.using_input(data), bases.using_stdout(subprocess.DEVNULL):
        bases.run(['tee', path])


def extract(archive_path, *, directory=None):
    archive_path = Path(archive_path)
    archive_type = utils.guess_archive_type(archive_path.name)
    if archive_type is utils.ArchiveTypes.TAR:
        tar_extract(archive_path, directory=directory)
    elif archive_type is utils.ArchiveTypes.ZIP:
        unzip(archive_path, directory=directory)
    else:
        ASSERT.unreachable('unknown archive type: {}', archive_path)


def tar_extract(tarball_path, *, directory=None, extra_args=()):
    """Extract tarball (into a specific directory)."""
    bases.run([
        'tar',
        '--extract',
        *('--file', tarball_path),
        *_tar_guess_compressor(Path(tarball_path).name),
        *(('--directory', directory) if directory else ()),
        *extra_args,
    ])


def _tar_guess_compressor(tarball_name):
    compressor = utils.guess_compressor(tarball_name)
    if compressor is utils.Compressors.UNCOMPRESSED:
        return ()
    elif compressor is utils.Compressors.BZIP2:
        return ('--bzip2', )
    elif compressor is utils.Compressors.GZIP:
        return ('--gzip', )
    elif compressor is utils.Compressors.XZ:
        return ('--xz', )
    else:
        return ASSERT.unreachable('unknown tarball suffix: {}', tarball_name)


def unzip(archive_path, *, directory=None):
    """Extract zip archive (into a specific directory)."""
    bases.run([
        'unzip',
        archive_path,
        *(('-d', directory) if directory else ()),
    ])


def make(targets=(), *, num_jobs=None):
    bases.run([
        'make',
        '--jobs=%d' % (os.cpu_count() + 2 if num_jobs is None else num_jobs),
        *targets,
    ])


def apt_get_update(*, assume='yes'):
    _apt_get('update', assume, ())


def apt_get_full_upgrade(*, assume='yes'):
    _apt_get('full-upgrade', assume, ())


def apt_get_install(packages, *, assume='yes'):
    _apt_get('install', assume, ASSERT.not_empty(packages))


def apt_get_clean(*, assume='yes'):
    _apt_get('clean', assume, ())


def _apt_get(command, assume, extra_args):
    bases.run([
        'apt-get',
        '--assume-%s' % ASSERT.in_(assume, ('yes', 'no')),
        command,
        *extra_args,
    ])


def wget(url, *, output_path=None, headers=()):
    bases.run([
        'wget',
        '--no-verbose',  # No progress bar (it looks awful in non-tty).
        *(('--output-document', output_path) if output_path else ()),
        *_wget_yield_headers(headers),
        url,
    ])


def _wget_yield_headers(headers):
    for header in headers:
        yield '--header'
        yield header


def git_clone(repo_url, *, repo_path=None, treeish=None):
    if repo_path is None:
        repo_path = bases.get_cwd() / _git_get_repo_name(repo_url)
    else:
        repo_path = Path(repo_path)
    mkdir(repo_path.parent)
    with bases.using_cwd(repo_path.parent):
        bases.run(['git', 'clone', repo_url, repo_path.name])
    with bases.using_cwd(repo_path):
        if treeish:
            bases.run(['git', 'checkout', treeish])
        if (repo_path / '.gitmodules').exists():
            bases.run([
                'git',
                'submodule',
                'update',
                '--init',
                '--checkout',
                '--recursive',
            ])


def _git_get_repo_name(repo_url):
    path = utils.get_url_path(repo_url)
    if path.suffix == '.git':
        return path.stem
    else:
        return path.name
