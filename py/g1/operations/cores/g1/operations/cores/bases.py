__all__ = [
    'copy_exec',
    'get_repo_path',
    'get_zipapp_target_path',
    'make_dir',
    'set_dir_attrs',
    'set_exec_attrs',
    'set_file_attrs',
]

import logging
import shutil
from pathlib import Path

from g1.apps import parameters
from g1.bases.assertions import ASSERT

LOG = logging.getLogger(__name__)

PARAMS = parameters.define(
    'g1.operations',
    parameters.Namespace(
        repository=parameters.Parameter(
            Path('/var/lib/g1/operations'),
            'path to the repository directory',
            convert=Path,
            validate=Path.is_absolute,
            format=str,
        ),
        application_group=parameters.Parameter(
            'plumber',
            'set application group',
            validate=bool,  # Check not empty.
        ),
        zipapp_directory=parameters.Parameter(
            Path('/usr/local/bin'),
            'path to install zipapp',
            convert=Path,
            validate=Path.is_absolute,
            format=str,
        ),
    ),
)

REPO_LAYOUT_VERSION = 'v1'


def get_repo_path():
    return PARAMS.repository.get() / REPO_LAYOUT_VERSION


def get_zipapp_target_path(name):
    return PARAMS.zipapp_directory.get() / name


def make_dir(path, *, parents=False):
    LOG.info('create directory: %s', path)
    path.mkdir(mode=0o750, parents=parents, exist_ok=True)
    # Use set_dir_attrs just in case ``path`` is already created.
    set_dir_attrs(path)


def copy_exec(src_path, dst_path):
    shutil.copyfile(src_path, dst_path)
    set_exec_attrs(dst_path)


def set_dir_attrs(path):
    ASSERT.predicate(path, Path.is_dir)
    path.chmod(0o750)
    _chown(path)


def set_file_attrs(path):
    ASSERT.predicate(path, Path.is_file)
    path.chmod(0o640)
    _chown(path)


def set_exec_attrs(path):
    ASSERT.predicate(path, Path.is_file)
    path.chmod(0o755)
    _chown(path)


def _chown(path):
    shutil.chown(path, 'root', PARAMS.application_group.get())
