__all__ = [
    'add_arguments',
    'ensure_not_root',
    'process_arguments',
    # Scripting helpers.
    'execute',
    'execute_many',
    'remove_tree',
    'systemctl',
    'tar_extract',
    'tee',
    'wget',
    # Helper classes.
    'FileLock',
]

import errno
import fcntl
import getpass
import logging
import os
from functools import partial
from subprocess import PIPE, Popen, call, check_call, check_output


LOG = logging.getLogger(__name__)
LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'


DRY_RUN = False


def ensure_not_root():
    if getpass.getuser() == 'root':
        raise RuntimeError('run by root')


def add_arguments(parser):
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help="""verbose output""")
    parser.add_argument(
        '--dry-run', action='store_true',
        help="""do not actually run commands""")


def process_arguments(_, args):
    if args.verbose > 0:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT)
    global DRY_RUN
    DRY_RUN = bool(args.dry_run)


### Scripting helpers.


def execute(cmd, *, cwd=None, return_output=False, check=True):
    cmd = list(map(str, cmd))
    cwd = str(cwd) if cwd is not None else None
    if LOG.isEnabledFor(logging.DEBUG):
        LOG.debug('execute: %s # cwd = %s', ' '.join(cmd), cwd)
    if DRY_RUN:
        return
    if return_output:
        caller = check_output
    elif check:
        caller = check_call
    else:
        caller = call
    return caller(cmd, cwd=cwd)


def execute_many(cmds, *, cwd=None):
    for cmd in cmds:
        execute(cmd, cwd=cwd)


def remove_tree(path):
    execute(['sudo', 'rm', '--force', '--recursive', path])


def systemctl(command, name, *, sudo=True, **kwargs):
    cmd = ['systemctl', '--quiet', command, name]
    if sudo:
        cmd.insert(0, 'sudo')
    return execute(cmd, **kwargs)


systemctl.enable = partial(systemctl, 'enable')
systemctl.disable = partial(systemctl, 'disable')
systemctl.is_enabled = partial(systemctl, 'is-enabled', sudo=False)


systemctl.start = partial(systemctl, 'start')
systemctl.stop = partial(systemctl, 'stop')
systemctl.is_active = partial(systemctl, 'is-active', sudo=False)


def tar_extract(tarball_path, *, sudo=False, tar_extra_args=(), **kwargs):
    cmd = ['tar', '--extract', '--file', tarball_path]
    if sudo:
        cmd.insert(0, 'sudo')

    output = execute(['file', tarball_path], return_output=True)
    if not output:
        if not DRY_RUN:
            raise RuntimeError('command `file` no output: %s' % tarball_path)
    elif b'gzip compressed data' in output:
        cmd.append('--gzip')
    elif b'bzip2 compressed data' in output:
        cmd.append('--bzip2')
    elif b'XZ compressed data' in output:
        cmd.append('--xz')

    cmd.extend(tar_extra_args)

    return execute(cmd, **kwargs)


def tee(output_path, writer, *, sudo=False):
    cmd = ['tee', str(output_path)]
    if sudo:
        cmd.insert(0, 'sudo')
    if LOG.isEnabledFor(logging.DEBUG):
        LOG.debug('execute: %s', ' '.join(cmd))
    if DRY_RUN:
        return
    with Popen(cmd, stdin=PIPE) as proc:
        retcode = 0
        try:
            writer(proc.stdin)
            proc.stdin.close()
        except Exception:
            proc.kill()
            raise
        finally:
            retcode = proc.wait()
        if retcode != 0:
            raise RuntimeError('tee %s: rc=%d', output_path, retcode)


def wget(uri, output_path, *, sudo=False, **kwargs):
    cmd = ['wget']
    if not LOG.isEnabledFor(logging.DEBUG):
        cmd.append('--no-verbose')  # No progress bar.
    cmd.extend([
        '--output-document', output_path,
        uri,
    ])
    if sudo:
        cmd.insert(0, 'sudo')
    return execute(cmd, **kwargs)


### Helper classes.


class FileLock:

    def __init__(self, path):
        self.path = path
        self._lock_fd = None
        self._lock_count = 0

    def acquire(self, blocking=True):

        if not self.path.exists():
            execute(['sudo', 'mkdir', '--parents', self.path.parent])
            execute(['sudo', 'touch', self.path])

        if self._lock_fd is None:
            fd = os.open(str(self.path), os.O_RDONLY)

            lock_mode = fcntl.LOCK_EX
            if not blocking:
                lock_mode |= fcntl.LOCK_NB
            try:
                fcntl.flock(fd, lock_mode)

            except BlockingIOError as exc:
                if exc.errno == errno.EWOULDBLOCK:
                    # Cannot acquire lock.
                    return False
                raise

            else:
                # Successfully acquired lock.
                fd, self._lock_fd = None, fd

            finally:
                if fd is not None:
                    os.close(fd)

        self._lock_count += 1
        return True

    def release(self):
        if self._lock_fd is None:
            raise RuntimeError("cannot release un-acquired lock")
        assert self._lock_count > 0
        self._lock_count -= 1
        if self._lock_count == 0:
            fd, self._lock_fd = self._lock_fd, None
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def __enter__(self):
        self.acquire()

    def __exit__(self, *_):
        self.release()
