"""Generic helper functions."""

__all__ = [
    'call',
    'ensure_directory',
    'sync_files',
    'tar_extract',
    'wget',
]

import logging
from pathlib import Path
from subprocess import check_call


LOG = logging.getLogger(__name__)


def call(args, **kwargs):
    """Log and then call subprocess.check_call."""
    if LOG.isEnabledFor(logging.DEBUG):
        LOG.debug('call: %s', ' '.join(args))
    check_call(args, **kwargs)


def ensure_directory(path, mode=0o777):
    """Create a directory if it does not exists."""
    # exist_ok is added to Path.mkdir until Python 3.5 :(
    path = Path(path)
    if path.exists():
        if not path.is_dir():
            raise RuntimeError('not a directory: %s' % path)
        return
    LOG.debug('make directory: %s', path)
    path.mkdir(mode=mode, parents=True)


def sync_files(srcs, dst, *, excludes=(), sudo=False):
    """Copy files with rsync."""
    cmd = ['rsync', '--archive', '--relative']
    if sudo:
        cmd.insert(0, 'sudo')
    for exclude in excludes:
        cmd.extend(['--exclude', str(exclude)])
    cmd.extend(map(str, srcs))
    cmd.append(str(dst))
    call(cmd)


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
    cmd = ['tar', '--extract', '--file', str(tarball_path)]
    if compress_flag:
        cmd.append(compress_flag)
    if output_path:
        cmd.extend(['--directory', str(output_path)])
    LOG.info('extract %s', tarball_path)
    check_call(cmd)


def wget(uri, output_path=None):
    cmd = ['wget', uri]
    if output_path:
        cmd.extend(['--output-document', str(output_path)])
    LOG.info('download %s', uri)
    check_call(cmd)
