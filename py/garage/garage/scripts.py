"""Helpers for writing scripts."""

__all__ = [
    # Context manipulation
    'directory',
    'dry_run',
    'recording_commands',
    'using_sudo',
    # Forming and running commands
    'execute',
    'make_command',
    # Commands
    'apt_get_full_upgrade',
    'apt_get_install',
    'apt_get_update',
    'git_clone',
    'mkdir',
    'rsync',
    'systemctl_disable',
    'systemctl_enable',
    'systemctl_is_active',
    'systemctl_is_enabled',
    'systemctl_start',
    'systemctl_stop',
    'tar_create',
    'tar_extract',
    'unzip',
    'wget',
    # Generic helpers
    'ensure_directory',
    'ensure_file',
    'ensure_not_root',
    'insert_path',
    'install_dependencies',
]

from pathlib import Path
import collections
import contextlib
import getpass
import functools
import logging
import os
import os.path
import subprocess
import threading


LOG = logging.getLogger(__name__)


LOCAL = threading.local()


# Context entries
DIRECTORY = 'directory'
DRY_RUN = 'dry_run'
RECORDING_COMMANDS = 'recording_commands'
USING_SUDO = 'using_sudo'


def _get_stack():
    try:
        return LOCAL.stack
    except AttributeError:
        LOCAL.stack = [collections.ChainMap()]
        return LOCAL.stack


def _get_context():
    return _get_stack()[-1]


@contextlib.contextmanager
def _enter_context(cxt, retval=None):
    stack = _get_stack()
    stack.append(stack[-1].new_child(cxt))
    try:
        yield retval
    finally:
        stack.pop()


def directory(path):
    """Use this directory for the following commands."""
    if path:
        return _enter_context({DIRECTORY: path})
    else:
        return _enter_context({})


def dry_run(dry_run_=True):
    """Do not actually run commands."""
    return _enter_context({DRY_RUN: dry_run_})


def recording_commands():
    """Record the commands executed (this cannot be nested)."""
    assert RECORDING_COMMANDS not in _get_context()
    records = []
    return _enter_context({RECORDING_COMMANDS: records}, records)


def using_sudo(using_sudo_=True, envs=None):
    """Run following commands with `sudo`."""
    if using_sudo_:
        return _enter_context({USING_SUDO: {'envs': envs}})
    else:
        assert not envs, repr(envs)
        return _enter_context({USING_SUDO: None})


def make_command(args):
    args = list(map(str, args))
    context = _get_context()
    using_sudo_ = context.get(USING_SUDO)
    if using_sudo_:
        sudo_args = ['sudo']
        for name in using_sudo_['envs'] or ():
            value = os.environ.get(name)
            if value:
                sudo_args.append('%s=%s' % (name, value))
        args[:0] = sudo_args
    return args


def execute(args, *, check=True, capture_stdout=False, capture_stderr=False):
    """Execute an external command."""
    context = _get_context()

    cwd = context.get(DIRECTORY)

    cmd = make_command(args)
    if LOG.isEnabledFor(logging.DEBUG):
        LOG.debug('execute: %s # cwd = %r', ' '.join(cmd), cwd)

    records = context.get(RECORDING_COMMANDS)
    if records is not None:
        records.append(cmd)

    if context.get(DRY_RUN):
        return (0, None, None)

    # Put check after DRY_RUN
    if cwd and not os.path.isdir(cwd):
        raise RuntimeError('not a directory: %r' % cwd)

    proc = subprocess.run(
        cmd,
        check=check,
        stdout=subprocess.PIPE if capture_stdout else None,
        stderr=subprocess.PIPE if capture_stderr else None,
        cwd=cwd,
    )
    return (
        proc.returncode,
        proc.stdout if capture_stdout else None,
        proc.stderror if capture_stderr else None,
    )


### Commands


# We depend on these Debian packages (excluding systemd).
DEBIAN_PACKAGES = [
    'git',
    'rsync',
    'tar',
    'unzip',
    'wget',
]


def apt_get_update():
    execute(['apt-get', 'update'])


def apt_get_full_upgrade():
    execute(['sudo', 'apt-get', '--yes', 'full-upgrade'])


def apt_get_install(pkgs):
    if not pkgs:
        return
    cmd = ['apt-get', 'install', '--yes']
    cmd.extend(pkgs)
    execute(cmd)


def git_clone(repo, local_path=None, checkout=None):
    if local_path:
        local_path.mkdir(parents=True)
    with directory(local_path):
        cmd = ['git', 'clone', repo]
        if local_path:
            cmd.append('.')
        execute(cmd)
        if checkout:
            execute(['git', 'checkout', checkout])


def mkdir(path):
    execute(['mkdir', '--parents', path])


def rsync(srcs, dst, *,
          delete=False,
          relative=False,
          includes=(), excludes=()):
    if not srcs:
        LOG.warning('rsync: empty srcs: %r', srcs)
        return
    cmd = ['rsync', '--archive']
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


def _systemctl(command, name):
    cmd = ['systemctl', '--quiet', command, name]
    return execute(cmd)


systemctl_enable = functools.partial(_systemctl, 'enable')
systemctl_disable = functools.partial(_systemctl, 'disable')
systemctl_is_enabled = functools.partial(_systemctl, 'is-enabled')


systemctl_start = functools.partial(_systemctl, 'start')
systemctl_stop = functools.partial(_systemctl, 'stop')
systemctl_is_active = functools.partial(_systemctl, 'is-active')


def tar_create(src_dir, srcs, tarball_path, tar_extra_flags=()):
    """Create a tarball."""
    src_dir = Path(src_dir)
    cmd = [
        'tar',
        '--create',
        '--file', Path(tarball_path).absolute(),
        '--directory', src_dir,
    ]
    cmd.extend(tar_extra_flags)
    for src in srcs:
        src = Path(src)
        if src.is_absolute():
            src = src.relative_to(src_dir)
        cmd.append(src)
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
    execute(cmd)


def unzip(zip_path, output_path=None):
    cmd = ['unzip', zip_path]
    if output_path:
        cmd.extend(['-d', output_path])
    execute(cmd)


def wget(uri, output_path=None, headers=()):
    cmd = ['wget']
    if not LOG.isEnabledFor(logging.DEBUG):
        cmd.append('--no-verbose')  # No progress bar
    if output_path:
        cmd.extend(['--output-document', output_path])
    for header in headers:
        cmd.extend(['--header', header])
    cmd.append(uri)
    execute(cmd)


### Generic helpers


def ensure_directory(path):
    """Raise FileNotFoundError if not a directory or does not exist."""
    path = Path(path)
    if not path.is_dir() and not _get_context().get(DRY_RUN):
        raise FileNotFoundError('not a directory: %s' % path)
    return path


def ensure_file(path):
    """Raise FileNotFoundError if not a file or does not exist."""
    path = Path(path)
    if not path.is_file() and not _get_context().get(DRY_RUN):
        raise FileNotFoundError('not a file: %s' % path)
    return path


def ensure_not_root():
    if getpass.getuser() == 'root':
        raise RuntimeError('script is ran by root')


def insert_path(path, *, var='PATH'):
    """Prepend path to a PATH-like environment variable."""
    paths = os.environ.get(var)
    paths = '%s:%s' % (path, paths) if paths else str(path)
    LOG.info('add %r to %s: %s', path, var, paths)
    os.environ[var] = paths


def install_dependencies():
    """Install command-line tools that we depend on (excluding systemd)."""
    missing_packages = []
    for package in DEBIAN_PACKAGES:
        cmd = ['dpkg-query', '--status', package]
        if execute(cmd, check=False, capture_stdout=True)[0] != 0:
            missing_packages.append(package)
    with using_sudo():
        apt_get_install(missing_packages)
