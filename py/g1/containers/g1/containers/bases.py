__all__ = [
    'cmd_init',
    'get_repo_path',
    # Command-line arguments.
    'grace_period_arguments',
    'make_grace_period_kwargs',
    # App-specific helpers.
    'chown_app',
    'chown_root',
    'make_dir',
    'rsync_copy',
    'setup_file',
]

import logging
import shutil
from pathlib import Path

from g1 import scripts
from g1.apps import parameters
from g1.bases import argparses
from g1.bases import datetimes
from g1.bases import oses
from g1.bases.assertions import ASSERT

LOG = logging.getLogger(__name__)

PARAMS = parameters.define(
    'g1.containers',
    parameters.Namespace(
        repository=parameters.Parameter(
            '/var/lib/g1/containers',
            doc='path to the repository directory',
            type=str,
        ),
        application_group=parameters.Parameter(
            'plumber',
            doc='set application group',
            type=str,
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
    oses.assert_group_exist(PARAMS.application_group.get())
    # For rsync_copy.
    scripts.check_command_exist('rsync')
    oses.assert_root_privilege()
    make_dir(get_repo_path(), 0o750, chown_app, parents=True)


def get_repo_path():
    return (Path(PARAMS.repository.get()) / REPO_LAYOUT_VERSION).absolute()


#
# Command-line arguments.
#

grace_period_arguments = argparses.argument(
    '--grace-period',
    type=argparses.parse_timedelta,
    default='24h',
    help='set grace period (default to %(default)s)',
)


def make_grace_period_kwargs(args):
    return {'expiration': datetimes.utcnow() - args.grace_period}


#
# App-specific helpers.
#


def chown_app(path):
    """Change owner to root and group to the application group."""
    shutil.chown(path, 'root', ASSERT.true(PARAMS.application_group.get()))


def chown_root(path):
    """Change owner and group to root."""
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
    scripts.run([
        'rsync',
        '--archive',
        *rsync_args,
        # Trailing slash is an rsync trick.
        '%s/' % src_path,
        dst_path,
    ])
