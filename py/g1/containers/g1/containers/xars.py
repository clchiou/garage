"""Manage executable archives.

NOTE: At the moment most of the repo directory permissions are not
world-readable; so xars are not world-executable.

Xar repository layout:

* Under ``xars`` there are xar directories.

* In a xar directory there are ``deps`` and ``exec``.

* ``deps`` is a directory of hard links to dependent image metadata.
  When a xar is running, it will hold a shared file lock on its hard
  link to prevent the hard link from being removed.

* ``exec`` is a symlink to the executable file in the image.
"""

__all__ = [
    # Public interface.
    'validate_name',
    # Expose to apps.
    'XAR_LIST_STRINGIFIERS',
    'cmd_cleanup',
    'cmd_exec',
    'cmd_init',
    'cmd_install',
    'cmd_list',
    'cmd_uninstall',
]

import argparse
import contextlib
import logging
import os
import re
from pathlib import Path

from g1.bases import argparses
from g1.bases.assertions import ASSERT

from . import bases
from . import images
from . import models

LOG = logging.getLogger(__name__)

# Allow xar names like "foo_bar.sh".
_NAME_PATTERN = re.compile(r'[\w\-.]+')


def validate_name(name):
    return ASSERT.predicate(name, _NAME_PATTERN.fullmatch)


#
# Top-level commands.  You need to check root privilege and acquire all
# file locks here.
#
# NOTE: When locking across ``images`` and ``xars`` directory, lock
# directories in ``xars`` first.
#
# TODO: For now our locking strategy is very naive - we simply lock the
# top-level directory.  If this turns out to cause a lot of lock
# contention, we should implement a finer-grained locking strategy.
#
#

_select_xar_arguments = argparses.argument(
    'name', type=validate_name, help='provide xar name'
)


def cmd_init():
    bases.assert_root_privilege()
    ASSERT.predicate(_get_xar_runner_script_dir_path(), Path.is_dir)
    bases.make_dir(_get_xars_repo_path(), 0o750, bases.chown_app)


@argparses.begin_parser(
    'install',
    **argparses.make_help_kwargs('install an image to xar repository'),
)
@images.select_image_arguments
@_select_xar_arguments
@argparses.argument(
    'exec', type=Path, help='provide executable path, relative to image root'
)
@argparses.end
def cmd_install(
    *,
    image_id=None,
    name=None,
    version=None,
    tag=None,
    xar_name,
    exec_relpath,
):
    bases.assert_root_privilege()
    with _locking_top_dirs():
        if image_id is None:
            image_id = ASSERT.not_none(
                images.find_id(name=name, version=version, tag=tag)
            )
        _install_xar_dir(
            _get_xar_dir_path(xar_name),
            image_id,
            ASSERT.not_predicate(exec_relpath, Path.is_absolute),
        )


_XAR_LIST_COLUMNS = frozenset((
    'xar',
    'id',
    'name',
    'version',
    'exec',
    'active',
))
_XAR_LIST_DEFAULT_COLUMNS = (
    'xar',
    'name',
    'version',
    'exec',
    'active',
)
XAR_LIST_STRINGIFIERS = {
    'exec': lambda exec_relpath: str(exec_relpath) if exec_relpath else '',
    'active': lambda active: 'true' if active else 'false',
}
ASSERT.issuperset(_XAR_LIST_COLUMNS, _XAR_LIST_DEFAULT_COLUMNS)
ASSERT.issuperset(_XAR_LIST_COLUMNS, XAR_LIST_STRINGIFIERS)


@argparses.begin_parser('list', **argparses.make_help_kwargs('list xars'))
@bases.formatter_arguments(_XAR_LIST_COLUMNS, _XAR_LIST_DEFAULT_COLUMNS)
@argparses.end
def cmd_list():
    # Don't need root privilege here.
    with _locking_top_dirs(read_only=True):
        for xar_dir_path in _iter_xar_dir_paths():
            yield from _list_xar_dir(xar_dir_path)


def _list_xar_dir(xar_dir_path):
    xar_name = _get_name(xar_dir_path)
    for image_id in _iter_ref_image_ids(xar_dir_path):
        metadata = images.read_metadata(images.get_image_dir_path(image_id))
        exec_path = _get_exec_path(xar_dir_path)
        if bases.lexists(exec_path):
            exec_relpath = _get_exec_relpath(exec_path.resolve(), image_id)
        else:
            exec_relpath = None
        active = bases.is_locked_by_other(
            _get_ref_path(xar_dir_path, image_id)
        )
        yield {
            'xar': xar_name,
            'id': image_id,
            'name': metadata.name,
            'version': metadata.version,
            'exec': exec_relpath,
            'active': active,
        }


@argparses.begin_parser('exec', **argparses.make_help_kwargs('execute xar'))
@_select_xar_arguments
@argparses.argument(
    'args', nargs=argparse.REMAINDER, help='provide executable arguments'
)
@argparses.end
def cmd_exec(xar_name, xar_args):
    # Don't need root privilege here.
    with bases.acquiring_shared(_get_xars_repo_path()):
        xar_dir_path = ASSERT.predicate(
            _get_xar_dir_path(xar_name), Path.is_dir
        )
        exec_abspath = ASSERT.predicate(
            _get_exec_path(xar_dir_path), Path.exists
        ).resolve()
        lock = bases.FileLock(
            _get_ref_path(xar_dir_path, _get_image_id(exec_abspath)),
            close_on_exec=False,
        )
        lock.acquire_shared()
    # TODO: Or should argv[0] be exec_abspath.name?
    argv = [xar_name]
    argv.extend(xar_args)
    LOG.debug('exec: path=%s, argv=%s', exec_abspath, argv)
    os.execv(str(exec_abspath), argv)


@argparses.begin_parser(
    'uninstall',
    **argparses.make_help_kwargs('uninstall an image from xar repository'),
)
@_select_xar_arguments
@argparses.end
def cmd_uninstall(xar_name):
    bases.assert_root_privilege()
    with _locking_top_dirs():
        xar_dir_path = _get_xar_dir_path(xar_name)
        if not xar_dir_path.exists():
            LOG.debug('xar does not exist: %s', xar_dir_path)
        else:
            _uninstall_xar_dir(xar_dir_path)
            _cleanup_xar_dir(xar_dir_path)


@argparses.begin_parser(
    'cleanup', **argparses.make_help_kwargs('clean up xar repository')
)
@argparses.end
def cmd_cleanup():
    bases.assert_root_privilege()
    with bases.acquiring_exclusive(_get_xars_repo_path()):
        for xar_dir_path in _get_xars_repo_path().iterdir():
            if not xar_dir_path.is_dir():
                LOG.info('remove unknown file: %s', xar_dir_path)
                xar_dir_path.unlink()
            else:
                _cleanup_xar_dir(xar_dir_path)


#
# Repo layout.
#

_XARS = 'xars'

_DEPS = 'deps'
_EXEC = 'exec'


def _get_xars_repo_path():
    return bases.get_repo_path() / _XARS


def _get_xar_dir_path(xar_name):
    return _get_xars_repo_path() / validate_name(xar_name)


def _get_name(xar_dir_path):
    return validate_name(xar_dir_path.name)


def _get_deps_path(xar_dir_path):
    return xar_dir_path / _DEPS


def _get_ref_path(xar_dir_path, image_id):
    return _get_deps_path(xar_dir_path) / models.validate_image_id(image_id)


def _get_exec_path(xar_dir_path):
    return xar_dir_path / _EXEC


def _get_image_rootfs_abspath(image_id):
    return (
        images.get_rootfs_path(images.get_image_dir_path(image_id)).resolve()
    )


def _get_exec_relpath(exec_abspath, image_id):
    return exec_abspath.relative_to(_get_image_rootfs_abspath(image_id))


def _get_image_id(exec_abspath):
    return models.validate_image_id(
        exec_abspath.relative_to(images.get_trees_path().resolve()).parts[0]
    )


def _get_exec_target(image_id, exec_relpath):
    rootfs_relpath = _get_image_rootfs_abspath(image_id).relative_to(
        bases.get_repo_path().resolve()
    )
    return Path('../..') / rootfs_relpath / exec_relpath


def _get_xar_runner_script_dir_path():
    return Path(bases.PARAMS.xar_runner_script_directory.get()).absolute()


def _get_xar_runner_script_path(xar_name):
    return _get_xar_runner_script_dir_path() / validate_name(xar_name)


#
# Locking strategy.
#


@contextlib.contextmanager
def _locking_top_dirs(*, read_only=False):
    if read_only:
        acquiring = bases.acquiring_shared
    else:
        acquiring = bases.acquiring_exclusive
    with acquiring(_get_xars_repo_path()):
        with bases.acquiring_shared(images.get_trees_path()):
            yield


#
# Xar directories.
#


def _iter_xar_dir_paths():
    for xar_dir_path in _get_xars_repo_path().iterdir():
        if not xar_dir_path.is_dir():
            LOG.debug('encounter unknown file under xars: %s', xar_dir_path)
        else:
            yield xar_dir_path


#
# Xar directory.
#


def _install_xar_dir(xar_dir_path, image_id, exec_relpath):
    if xar_dir_path.exists():
        _update_xar_dir(xar_dir_path, image_id, exec_relpath)
    else:
        _create_xar_dir(xar_dir_path, image_id, exec_relpath)


def _create_xar_dir(xar_dir_path, image_id, exec_relpath):
    LOG.info('create xar: %s', xar_dir_path)
    xar_name = _get_name(xar_dir_path)
    try:
        bases.make_dir(xar_dir_path, 0o750, bases.chown_app)
        bases.make_dir(_get_deps_path(xar_dir_path), 0o750, bases.chown_app)
        _add_ref_image_id(xar_dir_path, image_id)
        exec_path = _get_exec_path(xar_dir_path)
        exec_path.symlink_to(_get_exec_target(image_id, exec_relpath))
        ASSERT.predicate(exec_path, Path.exists)
        _create_xar_runner_script(xar_name)
    except:
        _remove_xar_dir(xar_dir_path)
        raise


def _update_xar_dir(xar_dir_path, image_id, exec_relpath):
    LOG.info('update xar: %s', xar_dir_path)
    if not _has_ref_image_id(xar_dir_path, image_id):
        _add_ref_image_id(xar_dir_path, image_id)
    exec_path = _get_exec_path(xar_dir_path)
    new_exec_path = exec_path.with_suffix('.tmp')
    new_exec_path.symlink_to(_get_exec_target(image_id, exec_relpath))
    new_exec_path.replace(exec_path)
    _create_xar_runner_script(_get_name(xar_dir_path))


def _uninstall_xar_dir(xar_dir_path):
    LOG.info('remove xar: %s', xar_dir_path)
    xar_name = _get_name(xar_dir_path)
    bases.delete_file(_get_xar_runner_script_path(xar_name))
    bases.delete_file(_get_exec_path(xar_dir_path))


def _cleanup_xar_dir(xar_dir_path):
    exec_path = _get_exec_path(xar_dir_path)
    if exec_path.exists():
        current_image_id = _get_image_id(exec_path.resolve())
    else:
        current_image_id = None
    active = False
    for image_id in _iter_ref_image_ids(xar_dir_path):
        if image_id == current_image_id:
            active = True
        elif not _maybe_remove_ref_image_id(xar_dir_path, image_id):
            active = True
    if not active:
        _remove_xar_dir(xar_dir_path)


def _remove_xar_dir(xar_dir_path):
    LOG.info('remove xar: %s', xar_dir_path)
    xar_name = _get_name(xar_dir_path)
    bases.delete_file(_get_xar_runner_script_path(xar_name))
    bases.delete_file(xar_dir_path)


#
# Dependent images.
#


def _iter_ref_image_ids(xar_dir_path):
    for ref_path in _get_deps_path(xar_dir_path).iterdir():
        if not ref_path.is_file():
            LOG.debug('encounter unknown file under deps: %s', ref_path)
        else:
            yield models.validate_image_id(ref_path.name)


def _has_ref_image_id(xar_dir_path, image_id):
    return _get_ref_path(xar_dir_path, image_id).exists()


def _add_ref_image_id(xar_dir_path, image_id):
    images.add_ref(image_id, _get_ref_path(xar_dir_path, image_id))


def _maybe_remove_ref_image_id(xar_dir_path, image_id):
    ref_path = _get_ref_path(xar_dir_path, image_id)
    if bases.is_locked_by_other(ref_path):
        return False
    else:
        ref_path.unlink()
        images.touch(image_id)
        return True


#
# Runner scripts.
#

# TODO: Can we skip this ``/bin/sh``?
_XAR_RUNNER_SCRIPT = '''\
#!/bin/sh
exec ctr xars exec "%s" "${@}"
'''


def _create_xar_runner_script(xar_name):
    path = _get_xar_runner_script_path(xar_name)
    path.write_text(_XAR_RUNNER_SCRIPT % xar_name)
    bases.setup_file(path, 0o755, bases.chown_root)
