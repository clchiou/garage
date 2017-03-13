"""Helpers for writing scripts."""

__all__ = [
    # Context manipulation
    'directory',
    'dry_run',
    'get_stdin',
    'get_stdout',
    'is_dry_run',
    'recording_commands',
    'redirecting',
    'using_sudo',
    # Forming and running commands
    'execute',
    'make_command',
    'pipeline',
    # Commands
    'apt_get_full_upgrade',
    'apt_get_install',
    'apt_get_update',
    'git_clone',
    'gunzip',
    'gzip',
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
    'ensure_checksum',
    'ensure_directory',
    'ensure_file',
    'ensure_not_root',
    'ensure_path',
    'ensure_str',
    'insert_path',
    'install_dependencies',
]

from pathlib import Path
import collections
import contextlib
import getpass
import functools
import hashlib
import logging
import os
import subprocess
import sys
import threading


LOG = logging.getLogger(__name__)


LOCAL = threading.local()


# Context entries
DIRECTORY = 'directory'
DRY_RUN = 'dry_run'
RECORDING_COMMANDS = 'recording_commands'
REDIRECTING = 'redirecting'
USING_SUDO = 'using_sudo'


def _get_stack():
    try:
        return LOCAL.stack
    except AttributeError:
        LOCAL.stack = [collections.ChainMap()]
        return LOCAL.stack


def _get_context():
    return _get_stack()[-1]


def _set_context(context):
    LOCAL.stack = [context]


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
        return _enter_context({DIRECTORY: ensure_path(path)})
    else:
        return _enter_context({})


def dry_run(dry_run_=True):
    """Do not actually run commands."""
    return _enter_context({DRY_RUN: dry_run_})


def is_dry_run():
    """Return True if dry-run is enabled in the current context."""
    return _get_context().get(DRY_RUN, False)


def recording_commands():
    """Record the commands executed (this cannot be nested)."""
    assert RECORDING_COMMANDS not in _get_context()
    records = []
    return _enter_context({RECORDING_COMMANDS: records}, records)


def redirecting(*, stdin=None, stdout=None, stderr=None):
    return _enter_context(
        {REDIRECTING: {'stdin': stdin, 'stdout': stdout, 'stderr': stderr}})


def get_stdin():
    """Return the redirected stdin in the current context."""
    return _get_context().get(REDIRECTING, {}).get('stdin')


def get_stdout():
    """Return the redirected stdout in the current context."""
    return _get_context().get(REDIRECTING, {}).get('stdout')


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
        # Fake a CompletedProcess object
        return subprocess.CompletedProcess(cmd, 0, b'', b'')

    # Put check after DRY_RUN
    if cwd and not cwd.is_dir():
        raise RuntimeError('not a directory: %r' % cwd)

    redirect = context.get(REDIRECTING) or {}
    stdin = redirect.get('stdin')
    stdout = subprocess.PIPE if capture_stdout else redirect.get('stdout')
    stderr = subprocess.PIPE if capture_stderr else redirect.get('stderr')

    return subprocess.run(
        cmd,
        check=check,
        stdin=stdin, stdout=stdout, stderr=stderr,
        cwd=ensure_str(cwd),  # PathLike will be added to Python 3.6
    )


def pipeline(commands, pipe_input=None, pipe_output=None):
    """Execute commands in a pipeline.

       Both the interface and the implementation of this function is
       awkward...
    """

    if pipe_input is not None and not isinstance(pipe_input, int):
        pipe_input = pipe_input.fileno()
    if pipe_output is not None and not isinstance(pipe_output, int):
        pipe_output = pipe_output.fileno()

    context = _get_context()
    all_done = threading.Barrier(len(commands))
    failed = threading.Event()

    def run_command(command, input_fd, output_fd):
        # Set context in the new thread
        _set_context(context)
        try:
            with redirecting(stdin=input_fd, stdout=output_fd):
                command()
        except Exception:
            LOG.exception('command err')
            failed.set()
        finally:
            if input_fd is not None:
                os.close(input_fd)
            if output_fd is not None:
                os.close(output_fd)
            all_done.wait()

    last_command = commands[-1]
    runners = []
    read_fd = pipe_input
    for command in commands:
        if command is last_command:
            next_read_fd, write_fd = None, pipe_output
        else:
            next_read_fd, write_fd = os.pipe()
        runner = threading.Thread(
            target=run_command,
            args=(command, read_fd, write_fd),
        )
        runner.start()
        runners.append(runner)
        read_fd = next_read_fd

    for runner in runners:
        runner.join()

    if failed.is_set():
        raise RuntimeError('pipeline fail')


### Commands


# We depend on these Debian packages (excluding systemd).
DEBIAN_PACKAGES = [
    'git',
    'gzip',
    'rsync',
    'tar',
    'unzip',
    'wget',
]


def apt_get_update():
    execute(['apt-get', 'update'])


def apt_get_full_upgrade():
    execute(['sudo', 'apt-get', '--yes', 'full-upgrade'])


def apt_get_install(packages, *, only_missing=True):
    if only_missing:
        missing = []
        for package in packages:
            with redirecting(stdout=subprocess.DEVNULL):
                cmd = ['dpkg-query', '--status', package]
                if execute(cmd, check=False).returncode != 0:
                    missing.append(package)
        packages = missing
    if not packages:
        return
    cmd = ['apt-get', 'install', '--yes']
    cmd.extend(packages)
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


def gunzip():
    """Decompress from stdin and write to stdout."""
    execute(['gunzip'])


def gzip(speed=6):
    """Compress from stdin and write to stdout.

       `speed` sets the compression speed, from 1 to 9, where 1 is the
       fastest (least compressed) and 9 the slowest (best compressed).
    """
    execute(['gzip', '-%d' % speed])


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
    """Create a tarball.

       If `tarball_path` is None, it will write to stdout.
    """
    src_dir = ensure_path(src_dir)
    cmd = [
        'tar',
        '--create',
        '--directory', src_dir,
    ]
    if tarball_path is None:
        cmd.extend(['--file', '-'])
    else:
        cmd.extend(['--file', ensure_path(tarball_path).absolute()])
    cmd.extend(tar_extra_flags)
    for src in srcs:
        src = ensure_path(src)
        if src.is_absolute():
            src = src.relative_to(src_dir)
        cmd.append(src)
    execute(cmd)


def tar_extract(tarball_path, output_path=None):
    """Extract a tarball."""
    tarball_path = ensure_path(tarball_path)
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
    if not sys.stdout.isatty():
        # No progress bar when not interactive (it looks awful)
        cmd.append('--no-verbose')
    if output_path:
        cmd.extend(['--output-document', output_path])
    for header in headers:
        cmd.extend(['--header', header])
    cmd.append(uri)
    execute(cmd)


### Generic helpers


def ensure_path(path):
    """Ensure `path` is an Path object (or None)."""
    if path is None:
        return path
    if not isinstance(path, Path):
        path = Path(path)
    return path


def ensure_str(obj):
    """Ensure `obj` is a str object (or None)."""
    return obj if obj is None else str(obj)


SUPPORTED_HASH_ALGORITHMS = {
    'md5': hashlib.md5,
    'sha1': hashlib.sha1,
    'sha512': hashlib.sha512,
}


def ensure_checksum(path, checksum):
    """Raise AssertionError if file's checksum does not match."""
    if is_dry_run():
        return
    hash_algorithm, hash_value = checksum.split('-', maxsplit=1)
    hasher = SUPPORTED_HASH_ALGORITHMS[hash_algorithm.lower()]()
    # I can't open(path, 'rb') because PathLike is added in Python 3.6
    with ensure_path(path).open('rb') as input_file:
        while True:
            data = input_file.read(4096)
            if not data:
                break
            hasher.update(data)
    digest = hasher.hexdigest()
    if digest != hash_value:
        raise AssertionError(
            'expect %s from %s but get %s' % (checksum, path, digest))


def ensure_directory(path):
    """Raise FileNotFoundError if not a directory or does not exist."""
    path = ensure_path(path)
    if not path.is_dir() and not is_dry_run():
        raise FileNotFoundError('not a directory: %s' % path)
    return path


def ensure_file(path):
    """Raise FileNotFoundError if not a file or does not exist."""
    path = ensure_path(path)
    if not path.is_file() and not is_dry_run():
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
    with using_sudo():
        apt_get_install(DEBIAN_PACKAGES)
