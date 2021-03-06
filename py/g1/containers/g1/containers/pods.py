"""Manage pods.

For now the pod repository layout is very simple:

* Under ``pods`` there are three top-level directories: active,
  graveyard, and tmp.

* ``active`` is the directory of prepared pod directories.

* ``active/<uuid>`` is a prepared pod directory.

* ``graveyard`` is the directory of pod directories to be removed.

* ``tmp`` is a scratchpad for preparing pod directory.

* In each pod directory, there are:

  * ``config`` is the pod configuration file in JSON format.
  * ``deps`` is a directory of hard links to dependent image metadata.
  * ``work`` is the work directory of the overlay file system.
  * ``upper`` is the upper directory of the overlay file system.
  * ``rootfs`` is the merged overlay file system.
"""

__all__ = [
    # Expose to apps.
    'POD_LIST_STRINGIFIERS',
    'POD_SHOW_STRINGIFIERS',
    'cmd_add_ref',
    'cmd_cat_config',
    'cmd_cleanup',
    'cmd_export_overlay',
    'cmd_generate_id',
    'cmd_init',
    'cmd_list',
    'cmd_prepare',
    'cmd_remove',
    'cmd_run',
    'cmd_run_prepared',
    'cmd_show',
]

import ctypes
import dataclasses
import errno
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import g1.files
from g1 import scripts
from g1.bases import argparses
from g1.bases import datetimes
from g1.bases import oses
from g1.bases.assertions import ASSERT
from g1.files import locks
from g1.texts import jsons
from g1.texts.columns import argparses as columns_argparses

from . import bases
from . import builders
from . import journals
from . import images
from . import models

LOG = logging.getLogger(__name__)

#
# Top-level commands.  You need to check root privilege and acquire all
# file locks here.
#
# NOTE: When locking across ``images`` and ``pods`` directory, lock
# directories in ``pods`` first.
#
# NOTE: When locking multiple top-level directories, lock them in
# alphabetical order to avoid deadlock.
#
# TODO: For now our locking strategy is very naive - we simply lock the
# top-level directory.  If this turns out to cause a lot of lock
# contention, we should implement a finer-grained locking strategy.
#


def _select_pod_arguments(*, positional):
    return argparses.argument(
        'id' if positional else '--id',
        type=models.validate_pod_id,
        help='set pod id',
    )


_provide_config_arguments = argparses.argument(
    'config', type=Path, help='provide path to pod config file'
)


def _stringify_last_updated(last_updated):
    return '' if last_updated is None else last_updated.isoformat()


def cmd_init():
    """Initialize the pod repository."""
    scripts.assert_command_exist('mount')
    scripts.assert_command_exist('umount')
    # Use systemd-nspawn of the host system for now.
    scripts.assert_command_exist('systemd-nspawn')
    oses.assert_root_privilege()
    bases.make_dir(_get_pod_repo_path(), 0o750, bases.chown_app)
    bases.make_dir(_get_active_path(), 0o750, bases.chown_app)
    bases.make_dir(_get_graveyard_path(), 0o750, bases.chown_app)
    bases.make_dir(_get_tmp_path(), 0o750, bases.chown_app)


_POD_LIST_COLUMNS = frozenset((
    'id',
    'name',
    'version',
    'images',
    'active',
    'last-updated',
    'ref-count',
))
_POD_LIST_DEFAULT_COLUMNS = (
    'id',
    'name',
    'version',
    'active',
    'last-updated',
    'ref-count',
)
POD_LIST_STRINGIFIERS = {
    'images': ' '.join,
    'active': lambda active: 'true' if active else 'false',
    'last-updated': _stringify_last_updated,
}
ASSERT.issuperset(_POD_LIST_COLUMNS, _POD_LIST_DEFAULT_COLUMNS)
ASSERT.issuperset(_POD_LIST_COLUMNS, POD_LIST_STRINGIFIERS)


@argparses.begin_parser('list', **argparses.make_help_kwargs('list pods'))
@columns_argparses.columnar_arguments(
    _POD_LIST_COLUMNS, _POD_LIST_DEFAULT_COLUMNS
)
@argparses.end
def cmd_list():
    # Don't need root privilege here.
    with locks.acquiring_shared(_get_active_path()):
        for pod_dir_path, config in _iter_configs():
            pod_status = _get_pod_status(pod_dir_path, config)
            yield {
                'id': _get_id(pod_dir_path),
                'name': config.name,
                'version': config.version,
                # Use _iter_image_ids rather than _iter_ref_image_ids
                # for ordered results.
                'images': list(_iter_image_ids(config)),
                'active': locks.is_locked_by_other(pod_dir_path),
                'last-updated': _get_last_updated(pod_status),
                'ref-count': _get_ref_count(pod_dir_path),
            }


_POD_SHOW_COLUMNS = frozenset((
    'name',
    'status',
    'last-updated',
    'ref-count',
))
_POD_SHOW_DEFAULT_COLUMNS = (
    'name',
    'status',
    'last-updated',
    'ref-count',
)
POD_SHOW_STRINGIFIERS = {
    'status': lambda status: '' if status is None else str(status),
    'last-updated': _stringify_last_updated,
}
ASSERT.issuperset(_POD_SHOW_COLUMNS, _POD_SHOW_DEFAULT_COLUMNS)
ASSERT.issuperset(_POD_SHOW_COLUMNS, POD_SHOW_STRINGIFIERS)


@argparses.begin_parser(
    'show', **argparses.make_help_kwargs('show pod status')
)
@columns_argparses.columnar_arguments(
    _POD_SHOW_COLUMNS, _POD_SHOW_DEFAULT_COLUMNS
)
@_select_pod_arguments(positional=True)
@argparses.end
def cmd_show(pod_id):
    # Don't need root privilege here.
    with locks.acquiring_shared(_get_active_path()):
        pod_dir_path = ASSERT.predicate(_get_pod_dir_path(pod_id), Path.is_dir)
        config = _read_config(pod_dir_path)
        pod_status = _get_pod_status(pod_dir_path, config)
        return [{
            'name': app.name,
            'status': pod_status.get(app.name, (None, None))[0],
            'last-updated': pod_status.get(app.name, (None, None))[1],
            'ref-count': _get_ref_count(pod_dir_path),
        } for app in config.apps]


@argparses.begin_parser(
    'cat-config', **argparses.make_help_kwargs('show pod config')
)
@_select_pod_arguments(positional=True)
@argparses.end
def cmd_cat_config(pod_id, output):
    config_path = ASSERT.predicate(
        _get_orig_config_path(_get_pod_dir_path(pod_id)), Path.is_file
    )
    output.write(config_path.read_bytes())


@argparses.begin_parser(
    'generate-id', **argparses.make_help_kwargs('generate a random pod id')
)
@argparses.end
def cmd_generate_id(output):
    output.write(models.generate_pod_id())
    output.write('\n')


@argparses.begin_parser('run', **argparses.make_help_kwargs('run a pod'))
@_select_pod_arguments(positional=False)
@_provide_config_arguments
@argparses.end
def cmd_run(pod_id, config_path, *, debug=False):
    oses.assert_root_privilege()
    cmd_prepare(pod_id, config_path)
    _run_pod(pod_id, debug=debug)


@argparses.begin_parser(
    'prepare', **argparses.make_help_kwargs('prepare a pod')
)
@_select_pod_arguments(positional=False)
@_provide_config_arguments
@argparses.end
def cmd_prepare(pod_id, config_path):
    """Prepare a pod directory, or no-op if pod exists."""
    oses.assert_root_privilege()
    # Make sure that it is safe to create a pod with this ID.
    ASSERT.not_equal(
        models.pod_id_to_machine_id(pod_id),
        models.read_host_machine_id(),
    )
    # Check before really preparing the pod.
    if g1.files.lexists(_get_pod_dir_path(pod_id)):
        LOG.info('skip duplicated pod: %s', pod_id)
        return
    config = jsons.load_dataobject(models.PodConfig, config_path)
    tmp_path = _create_tmp_pod_dir()
    try:
        _prepare_pod_dir(tmp_path, pod_id, config)
        with locks.acquiring_exclusive(_get_active_path()):
            if _maybe_move_pod_dir_to_active(tmp_path, pod_id):
                tmp_path = None
            else:
                LOG.info('skip duplicated pod: %s', pod_id)
    finally:
        if tmp_path:
            _remove_pod_dir(tmp_path)


@argparses.begin_parser(
    'run-prepared', **argparses.make_help_kwargs('run a prepared pod')
)
@_select_pod_arguments(positional=True)
@argparses.end
def cmd_run_prepared(pod_id, *, debug=False):
    oses.assert_root_privilege()
    pod_dir_path = ASSERT.predicate(_get_pod_dir_path(pod_id), Path.is_dir)
    _lock_pod_dir_for_exec(pod_dir_path)
    if g1.files.is_empty_dir(_get_rootfs_path(pod_dir_path)):
        LOG.warning('overlay is not mounted; system probably rebooted')
        _mount_overlay(pod_dir_path, _read_config(pod_dir_path))
    _run_pod(pod_id, debug=debug)


# NOTE: This prevents a pod from being removed or cleaned up; if not
# careful, you might have pod "leak" issue.
@argparses.begin_parser(
    'add-ref', **argparses.make_help_kwargs('add a reference to pod')
)
@_select_pod_arguments(positional=True)
@argparses.argument('target', type=Path, help='provide target path')
@argparses.end
def cmd_add_ref(pod_id, target_path):
    oses.assert_root_privilege()
    with locks.acquiring_shared(_get_active_path()):
        _add_ref(
            ASSERT.predicate(_get_pod_dir_path(pod_id), Path.is_dir),
            ASSERT.not_predicate(target_path, g1.files.lexists),
        )
    return 0


@argparses.begin_parser(
    'export-overlay', **argparses.make_help_kwargs('export overlay files')
)
@argparses.argument(
    '--include',
    action=argparses.AppendConstAndValueAction,
    dest='filter',
    const='include',
    help='add an overlay path filter'
)
@argparses.argument(
    '--exclude',
    action=argparses.AppendConstAndValueAction,
    dest='filter',
    const='exclude',
    help='add an overlay path filter'
)
@_select_pod_arguments(positional=True)
@argparses.argument('output', type=Path, help='provide output path')
@argparses.end
def cmd_export_overlay(pod_id, output_path, filter_patterns, *, debug=False):
    oses.assert_root_privilege()
    ASSERT.not_predicate(output_path, g1.files.lexists)
    # Exclude pod-generated files.
    # TODO: Right now we hard-code the list, but this is fragile.
    filter_args = [
        '--exclude=/etc/machine-id',
        '--exclude=/var/lib/dbus/machine-id',
        '--exclude=/etc/hostname',
        '--exclude=/etc/hosts',
        '--exclude=/etc/systemd',
        '--exclude=/etc/.pwd.lock',
        '--exclude=/etc/mtab',
        # Remove distro unit files.
        '--exclude=/etc/systemd/system',
        '--exclude=/lib/systemd/system',
        '--exclude=/usr/lib/systemd/system',
    ]
    filter_args.extend('--%s=%s' % pair for pair in filter_patterns)
    if debug:
        # Log which files are included/excluded due to filter rules.
        filter_args.append('--debug=FILTER2')
    with locks.acquiring_exclusive(_get_active_path()):
        pod_dir_path = ASSERT.predicate(_get_pod_dir_path(pod_id), Path.is_dir)
        pod_dir_lock = ASSERT.true(locks.try_acquire_exclusive(pod_dir_path))
    try:
        upper_path = _get_upper_path(pod_dir_path)
        bases.rsync_copy(upper_path, output_path, filter_args)
    finally:
        pod_dir_lock.release()
        pod_dir_lock.close()


@argparses.begin_parser(
    'remove', **argparses.make_help_kwargs('remove an exited pod')
)
@_select_pod_arguments(positional=True)
@argparses.end
def cmd_remove(pod_id):
    """Remove a pod, or no-op if pod does not exist."""
    oses.assert_root_privilege()
    pod_dir_path = _get_pod_dir_path(pod_id)
    with locks.acquiring_exclusive(_get_active_path()):
        if not pod_dir_path.is_dir():
            LOG.debug('pod does not exist: %s', pod_id)
            return
        ASSERT.less_or_equal(_get_ref_count(pod_dir_path), 1)
        pod_dir_lock = locks.acquire_exclusive(pod_dir_path)
    try:
        with locks.acquiring_exclusive(_get_graveyard_path()):
            grave_path = _move_pod_dir_to_graveyard(pod_dir_path)
        journals.remove_journal_dir(pod_id)
        _remove_pod_dir(grave_path)
    finally:
        pod_dir_lock.release()
        pod_dir_lock.close()


@argparses.begin_parser(
    'cleanup', **argparses.make_help_kwargs('clean up pod repository')
)
@bases.grace_period_arguments
@argparses.end
def cmd_cleanup(expiration):
    oses.assert_root_privilege()
    _cleanup_active(expiration)
    for top_dir_path in (
        _get_tmp_path(),
        _get_graveyard_path(),
    ):
        with locks.acquiring_exclusive(top_dir_path):
            _cleanup_top_dir(top_dir_path)


def _cleanup_active(expiration):
    LOG.info('remove pods before: %s', expiration)
    with locks.acquiring_exclusive(_get_active_path()):
        for pod_dir_path, config in _iter_configs():
            pod_id = _get_id(pod_dir_path)
            if _get_ref_count(pod_dir_path) > 1:
                LOG.debug('pod is still referenced: %s', pod_id)
                continue
            pod_dir_lock = locks.try_acquire_exclusive(pod_dir_path)
            if not pod_dir_lock:
                LOG.debug('pod is still active: %s', pod_id)
                continue
            try:
                pod_status = _get_pod_status(pod_dir_path, config)
                last_updated = _get_last_updated(pod_status)
                if last_updated is None:
                    # Prevent cleaning up just-prepared pod directory.
                    last_updated = datetimes.utcfromtimestamp(
                        _get_config_path(pod_dir_path).stat().st_mtime
                    )
                if last_updated < expiration:
                    with locks.acquiring_exclusive(_get_graveyard_path()):
                        LOG.info('clean up pod: %s', pod_id)
                        _move_pod_dir_to_graveyard(pod_dir_path)
                    journals.remove_journal_dir(pod_id)
            finally:
                pod_dir_lock.release()
                pod_dir_lock.close()


#
# Locking strategy.
#


def _create_tmp_pod_dir():
    """Create and then lock a temporary directory.

    NOTE: This lock is not released/close on exec.
    """
    tmp_dir_path = _get_tmp_path()
    with locks.acquiring_exclusive(tmp_dir_path):
        tmp_path = Path(tempfile.mkdtemp(dir=tmp_dir_path))
        try:
            bases.setup_file(tmp_path, 0o750, bases.chown_app)
            _lock_pod_dir_for_exec(tmp_path)
        except:
            tmp_path.rmdir()
            raise
        return tmp_path


def _lock_pod_dir_for_exec(pod_dir_path):
    """Lock pod directory.

    NOTE: This lock is not released/close on exec.
    """
    pod_dir_lock = locks.FileLock(pod_dir_path, close_on_exec=False)
    pod_dir_lock.acquire_exclusive()


#
# Repo layout.
#

_PODS = 'pods'

_ACTIVE = 'active'
_GRAVEYARD = 'graveyard'
_TMP = 'tmp'

# Entries in a pod directory.
_CONFIG = 'config'
_DEPS = 'deps'
_WORK = 'work'
_UPPER = 'upper'
_ROOTFS = 'rootfs'


def _get_pod_repo_path():
    return bases.get_repo_path() / _PODS


def _get_active_path():
    return _get_pod_repo_path() / _ACTIVE


def _get_graveyard_path():
    return _get_pod_repo_path() / _GRAVEYARD


def _get_tmp_path():
    return _get_pod_repo_path() / _TMP


def _get_pod_dir_path(pod_id):
    return _get_active_path() / models.validate_pod_id(pod_id)


def _get_id(pod_dir_path):
    return models.validate_pod_id(pod_dir_path.name)


def _get_config_path(pod_dir_path):
    return pod_dir_path / _CONFIG


def _get_orig_config_path(pod_dir_path):
    return _get_config_path(pod_dir_path).with_suffix('.orig')


def _get_deps_path(pod_dir_path):
    return pod_dir_path / _DEPS


def _get_work_path(pod_dir_path):
    return pod_dir_path / _WORK


def _get_upper_path(pod_dir_path):
    return pod_dir_path / _UPPER


def _get_rootfs_path(pod_dir_path):
    return pod_dir_path / _ROOTFS


#
# Functions below require caller acquiring locks.
#

#
# Top-level directories.
#


def _cleanup_top_dir(top_dir_path):
    for path in top_dir_path.iterdir():
        if not path.is_dir():
            LOG.info('remove unknown file: %s', path)
            path.unlink()
            continue
        lock = locks.try_acquire_exclusive(path)
        if not lock:
            continue
        try:
            _remove_pod_dir(path)
        finally:
            lock.release()
            lock.close()


#
# Pod directories.
#


def _iter_pod_dir_paths():
    for pod_dir_path in _get_active_path().iterdir():
        if not pod_dir_path.is_dir():
            LOG.debug('encounter unknown file under active: %s', pod_dir_path)
        else:
            yield pod_dir_path


def _maybe_move_pod_dir_to_active(dir_path, pod_id):
    pod_dir_path = _get_pod_dir_path(pod_id)
    if g1.files.lexists(pod_dir_path):
        return False
    else:
        dir_path.rename(pod_dir_path)
        return True


def _move_pod_dir_to_graveyard(dir_path):
    dst_path = _get_graveyard_path() / dir_path.name
    if g1.files.lexists(dst_path):
        dst_path.with_name('%s_%s' % (dst_path.name, models.generate_pod_id()))
        LOG.debug(
            'rename duplicated pod directory under graveyard: %s -> %s',
            dir_path.name,
            dst_path.name,
        )
        ASSERT.not_predicate(dst_path, g1.files.lexists)
    dir_path.rename(dst_path)
    return dst_path


#
# Pod directory.
#


def _prepare_pod_dir(pod_dir_path, pod_id, config):
    LOG.info('prepare pod: %s', pod_id)
    _setup_pod_dir_barely(pod_dir_path, config)
    config = _add_ref_image_ids(pod_dir_path, config)
    _mount_overlay(pod_dir_path, config)
    rootfs_path = _get_rootfs_path(pod_dir_path)
    builders.generate_machine_id(
        rootfs_path,
        models.pod_id_to_machine_id(pod_id),
    )
    _generate_hostname(rootfs_path, pod_id)
    _generate_unit_files(rootfs_path, config)


def _setup_pod_dir_barely(pod_dir_path, config):
    _pod_dir_create_orig_config(pod_dir_path, config)
    bases.make_dir(_get_deps_path(pod_dir_path), 0o750, bases.chown_app)
    # Trivia: After overlay is mounted, root directory's mode is
    # actaully the same as upper's.
    bases.make_dir(_get_work_path(pod_dir_path), 0o755, bases.chown_root)
    bases.make_dir(_get_upper_path(pod_dir_path), 0o755, bases.chown_root)
    bases.make_dir(_get_rootfs_path(pod_dir_path), 0o755, bases.chown_root)


def _pod_dir_create_config(pod_dir_path, config):
    _write_config(config, pod_dir_path)
    bases.setup_file(_get_config_path(pod_dir_path), 0o640, bases.chown_app)


def _pod_dir_create_orig_config(pod_dir_path, config):
    _write_orig_config(config, pod_dir_path)
    bases.setup_file(
        _get_orig_config_path(pod_dir_path), 0o640, bases.chown_app
    )


def _remove_pod_dir(pod_dir_path):
    LOG.info('remove pod directory: %s', pod_dir_path)
    _umount_overlay(pod_dir_path)
    with locks.acquiring_shared(images.get_trees_path()):
        for ref_image_id in _iter_ref_image_ids(pod_dir_path):
            images.touch(ref_image_id)
    shutil.rmtree(pod_dir_path)


#
# Pod.
#


def _mount_overlay(pod_dir_path, config):
    rootfs_path = _get_rootfs_path(pod_dir_path)
    LOG.info('mount overlay: %s', rootfs_path)
    #
    # Since we should have added image refs, it is safe to access image
    # directories without locking them.
    #
    # NOTE: You cannot use _iter_ref_image_ids here as its result is not
    # ordered; you must use _iter_image_ids.
    #
    image_ids = list(_iter_image_ids(config))
    # Call reverse() because in overlay file system, lower directories
    # are ordered from high to low.
    image_ids.reverse()
    scripts.run([
        'mount',
        *('-t', 'overlay'),
        *(
            '-o',
            'lowerdir=%s,upperdir=%s,workdir=%s' % (
                ':'.join(
                    str(_get_image_rootfs_path(image_id))
                    for image_id in image_ids
                ),
                _get_upper_path(pod_dir_path),
                _get_work_path(pod_dir_path),
            ),
        ),
        'overlay',
        rootfs_path,
    ])


def _umount_overlay(pod_dir_path):
    rootfs_path = _get_rootfs_path(pod_dir_path)
    _umount(rootfs_path)
    # Just a sanity check that rootfs is really unmounted.
    ASSERT.predicate(rootfs_path, g1.files.is_empty_dir)


def _generate_hostname(rootfs_path, pod_id):
    hostname = models.generate_machine_name(pod_id)
    (rootfs_path / 'etc/hostname').write_text(hostname + '\n')
    (rootfs_path / 'etc/hosts').write_text(
        '127.0.0.1\tlocalhost\n'
        '127.0.1.1\t%s\n' % hostname
    )


def _generate_unit_files(rootfs_path, config):
    for app in config.apps:
        builders.generate_unit_file(
            rootfs_path, config.name, config.version, app
        )


def _run_pod(pod_id, *, debug=False):
    LOG.info('start pod: %s', pod_id)
    pod_dir_path = ASSERT.predicate(_get_pod_dir_path(pod_id), Path.is_dir)
    rootfs_path = _get_rootfs_path(pod_dir_path)
    config = _read_config(pod_dir_path)
    builders.clear_pod_app_exit_status(rootfs_path)
    #
    # * For now we do not worry too much about cross-platform issues; we
    #   assume that the pod is running in a host system with
    #   systemd-nspawn, journald, etc.
    #
    # * For now we do not support interactive pod.
    #
    args = [
        # Use systemd-nspawn of the host system (alternatively, we may
        # install and use systemd-nspawn in the base image, which is
        # probably more cross-platform).
        'systemd-nspawn',
        '--uuid=%s' % pod_id,
        '--machine=%s' % models.generate_machine_name(pod_id),
        '--register=yes',
        *(['--keep-unit'] if _is_running_from_system_service() else []),
        '--boot',
        '--directory=%s' % rootfs_path,
        *(_make_bind_argument(mount) for mount in config.mounts),
        *(_make_overlay_argument(overlay) for overlay in config.overlays),
        '--notify-ready=yes',
        '--link-journal=try-host',
        *([] if debug else ['--quiet']),
        '--',
        # I don't know why, but if you set
        #   --default-standard-output=journal+console
        # then ``machinectl shell`` will not work.
        *([] if debug else [
            '--log-target=null',
            '--show-status=no',
        ]),
    ]
    LOG.debug('run pod: args=%s', args)
    os.execvp(args[0], args)
    ASSERT.unreachable('unable to start pod: {}', pod_id)


def _make_bind_argument(mount):
    return '--bind%s=%s:%s' % (
        '-ro' if mount.read_only else '',
        ASSERT.not_contains(mount.source, ':'),
        ASSERT.not_contains(mount.target, ':'),
    )


def _make_overlay_argument(overlay):
    return '--overlay%s=%s:%s' % (
        '-ro' if overlay.read_only else '',
        ':'.join(
            ASSERT.not_contains(source, ':') for source in overlay.sources
        ),
        ASSERT.not_contains(overlay.target, ':'),
    )


#
# Configs.
#


def _iter_configs():
    for pod_dir_path in _iter_pod_dir_paths():
        yield pod_dir_path, _read_config(pod_dir_path)


def _read_config(pod_dir_path):
    return jsons.load_dataobject(
        models.PodConfig, _get_config_path(pod_dir_path)
    )


def _read_orig_config(pod_dir_path):
    return jsons.load_dataobject(
        models.PodConfig, _get_orig_config_path(pod_dir_path)
    )


def _write_config(config, pod_dir_path):
    jsons.dump_dataobject(config, _get_config_path(pod_dir_path))


def _write_orig_config(config, pod_dir_path):
    jsons.dump_dataobject(config, _get_orig_config_path(pod_dir_path))


def _iter_image_ids(config):
    """Search image IDs from image repo.

    It raises an error if any one of the image IDs cannot be found.

    NOTE: Caller has to lock image repo before calling this.
    """
    for image in config.images:
        if image.id:
            image_id = image.id
        else:
            image_id = ASSERT.not_none(
                images.find_id(
                    name=image.name,
                    version=image.version,
                    tag=image.tag,
                )
            )
        yield image_id


#
# Ref-count on config.
#


def _get_ref_count(pod_dir_path):
    try:
        return _get_config_path(pod_dir_path).stat().st_nlink
    except FileNotFoundError:
        return 0


def _add_ref(pod_dir_path, dst_path):
    os.link(
        ASSERT.predicate(_get_config_path(pod_dir_path), Path.is_file),
        dst_path,
    )


#
# Dependent images.
#


def _add_ref_image_ids(pod_dir_path, config):
    deps_path = _get_deps_path(pod_dir_path)
    with locks.acquiring_shared(images.get_trees_path()):
        # Replace pod config with resolved image IDs because tags may
        # change over time.
        new_images = []
        for image_id in _iter_image_ids(config):
            images.add_ref(image_id, deps_path / image_id)
            new_images.append(models.PodConfig.Image(id=image_id))
        new_config = dataclasses.replace(config, images=new_images)
    _pod_dir_create_config(pod_dir_path, new_config)
    return new_config


def _iter_ref_image_ids(pod_dir_path):
    """Iterate over ref image IDs.

    NOTE: The results are not ordered.
    """
    for ref_path in _get_deps_path(pod_dir_path).iterdir():
        if not ref_path.is_file():
            LOG.debug('encounter unknown file under deps: %s', ref_path)
        else:
            yield models.validate_image_id(ref_path.name)


def _get_image_rootfs_path(image_id):
    return images.get_rootfs_path(images.get_image_dir_path(image_id))


#
# Pod runtime state.
#


def _get_pod_status(pod_dir_path, config):
    rootfs_path = _get_rootfs_path(pod_dir_path)
    pod_status = {}
    for app in config.apps:
        status, mtime = builders.get_pod_app_exit_status(rootfs_path, app)
        if status is not None:
            pod_status[app.name] = (status, mtime)
    return pod_status


def _get_last_updated(pod_status):
    """Return the most recent last-updated."""
    return max((mtime for _, mtime in pod_status.values()), default=None)


#
# Helpers for mount/umount.
#

_UMOUNT_ERROR_WHITELIST = re.compile(br': not mounted\.$')


def _umount(path):
    ASSERT.not_predicate(path, Path.is_symlink)
    LOG.info('umount: %s', path)
    try:
        with scripts.doing_capture_stderr():
            scripts.run(['umount', path])
    except subprocess.CalledProcessError as exc:
        if _UMOUNT_ERROR_WHITELIST.search(exc.stderr, re.MULTILINE):
            LOG.debug('umount err: %s, %s', path, exc.stderr, exc_info=True)
        else:
            LOG.error('umount err: %s, %s', path, exc.stderr)
            raise


#
# Host system.
#


def _is_running_from_system_service():
    """True if running from a systemd service.

    Be conservative here and only return true when we are certain about
    it (as ``--keep-unit`` is a nice-to-have, not a must-have flag).

    NOTE: This function is derived from coreos/go-systemd project's
    ``runningFromSystemService`` function in util/util_cgo.go.
    """
    try:
        libsystemd = ctypes.cdll.LoadLibrary('libsystemd.so')
    except OSError:
        LOG.debug('unable to load libsystemd.so')
        return False
    try:
        sd_pid_get_owner_uid = libsystemd.sd_pid_get_owner_uid
    except AttributeError:
        LOG.debug('unable to load sd_pid_get_owner_uid')
        return False
    sd_pid_get_owner_uid.argtypes = (
        ctypes.c_int,  # pid_t
        ctypes.POINTER(ctypes.c_int),  # uid_t*
    )
    sd_pid_get_owner_uid.restype = ctypes.c_int
    uid = ctypes.c_int()
    rc = sd_pid_get_owner_uid(0, ctypes.byref(uid))
    if rc >= 0:
        return False
    if -rc not in (
        errno.ENOENT,  # systemd < 220
        errno.ENXIO,  # systemd 220 - 223
        errno.ENODATA,  # systemd >= 234
    ):
        return False
    return os.getsid(0) == os.getpid()
