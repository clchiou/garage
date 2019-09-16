__all__ = [
    'cmd_init',
    'get_repo_path',
    # Command-line arguments.
    'formatter_arguments',
    'grace_period_arguments',
    'make_formatter_kwargs',
    'make_grace_period_kwargs',
    'make_help_kwargs',
    # Extension to Path object.
    'delete_file',
    'is_empty_dir',
    'lexists',
    # App-specific helpers.
    'assert_group_exist',
    'assert_program_exist',
    'assert_root_privilege',
    'check_program_exist',
    'chown_app',
    'chown_root',
    'make_dir',
    'read_jsonobject',
    'rsync_copy',
    'setup_file',
    'write_jsonobject',
    # File lock.
    'FileLock',
    'NotLocked',
    'acquiring_exclusive',
    'acquiring_shared',
    'try_acquire_exclusive',
    'is_locked_by_other',
]

import contextlib
import dataclasses
import errno
import fcntl
import grp
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from g1.apps import parameters
from g1.bases import argparses
from g1.bases import dataclasses as g1_dataclasses
from g1.bases import datetimes
from g1.bases import functionals
from g1.bases.assertions import ASSERT

from . import formatters

LOG = logging.getLogger(__name__)

PARAMS = parameters.define(
    'g1.containers',
    parameters.Namespace(
        repository=parameters.Parameter(
            '/var/lib/g1-containers',
            doc='path to the repository directory',
            type=str,
        ),
        base_image_name=parameters.Parameter(
            'base',
            doc='set base image name',
            type=str,
        ),
        base_image_version=parameters.Parameter(
            '0.0.1',
            doc='set base image version',
            type=str,
        ),
        application_group=parameters.Parameter(
            # TODO: Choose an application group to replace "root".
            'root',
            doc='set application group',
            type=str,
        ),
        use_root_privilege=parameters.Parameter(
            True,
            doc='whether to check the process has root privilege '
            '(you may set this to false while testing)',
            type=bool,
        ),
        xar_runner_script_directory=parameters.Parameter(
            '/usr/local/bin',
            doc='path to the xar runner script directory',
            type=str,
        ),
    ),
)

REPO_LAYOUT_VERSION = 'v1'


def cmd_init():
    """Initialize the repository."""
    assert_group_exist(PARAMS.application_group.get())
    # For rsync_copy.
    check_program_exist('rsync')
    make_dir(get_repo_path(), 0o750, chown_app, parents=True)


def get_repo_path():
    return (Path(PARAMS.repository.get()) / REPO_LAYOUT_VERSION).absolute()


#
# Command-line arguments.
#


def formatter_arguments(columns, default_columns):
    return functionals.compose(
        argparses.argument(
            '--format',
            action=argparses.StoreEnumAction,
            default=formatters.Formats.TEXT,
            help='set output format (default: %(default_string)s)',
        ),
        argparses.argument(
            '--header',
            action=argparses.StoreBoolAction,
            default=True,
            help='enable/disable header output (default: %(default_string)s)',
        ),
        argparses.begin_argument(
            '--columns',
            type=lambda columns_str: ASSERT.all(
                list(filter(None, columns_str.split(','))),
                columns.__contains__,
            ),
            default=','.join(default_columns),
            help=(
                'set output columns (available columns are: %(columns)s) '
                '(default: %(default)s)'
            ),
        ),
        argparses.apply(
            lambda action:
            setattr(action, 'columns', ','.join(sorted(columns)))
        ),
        argparses.end,
    )


def make_formatter_kwargs(args):
    return {
        'format': args.format,
        'header': args.header,
        'columns': args.columns,
    }


grace_period_arguments = argparses.argument(
    '--grace-period',
    type=argparses.parse_timedelta,
    default='24h',
    help='set grace period (default to %(default)s)',
)


def make_grace_period_kwargs(args):
    return {'expiration': datetimes.utcnow() - args.grace_period}


def make_help_kwargs(help_text):
    return {
        'help': help_text,
        'description': '%s%s.' % (help_text[0].upper(), help_text[1:]),
    }


#
# Extension to Path object.
#


def is_empty_dir(path):
    """True on empty directory."""
    try:
        next(path.iterdir())
    except StopIteration:
        return True
    except (FileNotFoundError, NotADirectoryError):
        return False
    else:
        return False


def lexists(path):
    """True if a file or symlink exists.

    ``lexists`` differs from ``Path.exists`` when path points to a
    broken but existent symlink: The former returns true but the latter
    returns false.
    """
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    else:
        return True


def delete_file(path):
    """Delete a file, handling symlink to directory correctly."""
    if not lexists(path):
        pass
    elif not path.is_dir() or path.is_symlink():
        path.unlink()
    else:
        shutil.rmtree(path)


#
# App-specific helpers.
#


def assert_program_exist(program):
    # Assume it's unit testing if not use_root_privilege.
    if PARAMS.use_root_privilege.get():
        ASSERT.not_none(shutil.which(program))


def check_program_exist(program):
    # Assume it's unit testing if not use_root_privilege.
    if PARAMS.use_root_privilege.get():
        if not shutil.which(program):
            LOG.warning(
                'program %s does not exist; certain features are unavailable',
                program
            )


def assert_group_exist(name):
    # Assume it's unit testing if not use_root_privilege.
    if PARAMS.use_root_privilege.get():
        try:
            grp.getgrnam(name)
        except KeyError:
            raise AssertionError('expect group: %s' % name) from None


def assert_root_privilege():
    if PARAMS.use_root_privilege.get():
        ASSERT.equal(os.geteuid(), 0)


def chown_app(path):
    """Change owner to root and group to the application group."""
    if PARAMS.use_root_privilege.get():
        shutil.chown(
            path,
            'root',
            ASSERT.true(PARAMS.application_group.get()),
        )


def chown_root(path):
    """Change owner and group to root."""
    if PARAMS.use_root_privilege.get():
        shutil.chown(path, 'root', 'root')


def make_dir(path, mode, chown, *, parents=False, exist_ok=True):
    LOG.info('create directory: %s', path)
    path.mkdir(mode=mode, parents=parents, exist_ok=exist_ok)
    chown(path)


def setup_file(path, mode, chown):
    path.chmod(mode)
    chown(path)


def rsync_copy(src_path, dst_path, rsync_args=()):
    # We do NOT use ``shutil.copytree`` because shutil's file copy
    # functions in general do not preserve the file owner/group.
    LOG.info('copy: %s -> %s', src_path, dst_path)
    subprocess.run(
        [
            'rsync',
            '--archive',
            *rsync_args,
            '%s/' % src_path,
            str(dst_path),
        ],
        check=True,
    )


def read_jsonobject(type_, path):
    return g1_dataclasses.fromdict(type_, json.loads(path.read_bytes()))


def write_jsonobject(obj, path):
    path.write_text(json.dumps(dataclasses.asdict(obj)), encoding='utf-8')


#
# File lock.
#


class NotLocked(Exception):
    """Raise when file lock cannot be acquired."""


class FileLock:

    def __init__(self, path, *, close_on_exec=True):
        fd = os.open(path, os.O_RDONLY)
        try:
            # Actually, CPython's os.open always sets O_CLOEXEC.
            flags = fcntl.fcntl(fd, fcntl.F_GETFD)
            if close_on_exec:
                new_flags = flags | fcntl.FD_CLOEXEC
            else:
                new_flags = flags & ~fcntl.FD_CLOEXEC
            if new_flags != flags:
                fcntl.fcntl(fd, fcntl.F_SETFD, new_flags)
        except:
            os.close(fd)
            raise
        self._fd = fd

    def acquire_shared(self):
        self._acquire(fcntl.LOCK_SH)

    def acquire_exclusive(self):
        self._acquire(fcntl.LOCK_EX)

    def _acquire(self, operation):
        ASSERT.not_none(self._fd)
        # TODO: Should we add a retry here?
        try:
            fcntl.flock(self._fd, operation | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            if exc.errno != errno.EWOULDBLOCK:
                raise
            raise NotLocked from None

    def release(self):
        """Release file lock.

        It is safe to call release even if lock has not been acquired.
        """
        ASSERT.not_none(self._fd)
        fcntl.flock(self._fd, fcntl.LOCK_UN)

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


@contextlib.contextmanager
def acquiring_shared(path):
    lock = FileLock(path)
    try:
        lock.acquire_shared()
        yield lock
    finally:
        lock.release()
        lock.close()


@contextlib.contextmanager
def acquiring_exclusive(path):
    lock = FileLock(path)
    try:
        lock.acquire_exclusive()
        yield lock
    finally:
        lock.release()
        lock.close()


def try_acquire_exclusive(path):
    lock = FileLock(path)
    try:
        lock.acquire_exclusive()
    except NotLocked:
        lock.close()
        return None
    else:
        return lock


def is_locked_by_other(path):
    lock = try_acquire_exclusive(path)
    if lock:
        lock.release()
        lock.close()
        return False
    else:
        return True
