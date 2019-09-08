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
    'cmd_cat_config',
    'cmd_cleanup',
    'cmd_init',
    'cmd_list',
    'cmd_prepare',
    'cmd_remove',
    'cmd_run',
    'cmd_run_prepared',
    'cmd_show',
    'generate_id',
    'validate_id',
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
import typing
import uuid
from pathlib import Path

from g1.bases import datetimes
from g1.bases.assertions import ASSERT

from . import bases
from . import builders
from . import images

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


def cmd_init():
    """Initialize the pod repository."""
    bases.assert_root_privilege()
    for path, mode, chown in (
        (get_pod_repo_path(), 0o750, bases.chown_app),
        (get_active_path(), 0o750, bases.chown_app),
        (get_graveyard_path(), 0o750, bases.chown_app),
        (get_tmp_path(), 0o750, bases.chown_app),
    ):
        LOG.info('create directory: %s', path)
        path.mkdir(mode=mode, parents=False, exist_ok=True)
        chown(path)


def cmd_list():
    # Don't need root privilege here.
    with bases.acquiring_shared(get_active_path()):
        for pod_dir_path, config in iter_configs():
            pod_status = get_pod_status(pod_dir_path, config)
            yield {
                'id': get_id(pod_dir_path),
                'name': config.name,
                'version': config.version,
                # Use iter_image_ids rather than iter_ref_image_ids for
                # ordered results.
                'images': list(iter_image_ids(config)),
                'active': is_pod_dir_locked(pod_dir_path),
                'last-updated': get_last_updated(pod_status),
            }


def cmd_show(pod_id):
    # Don't need root privilege here.
    with bases.acquiring_shared(get_active_path()):
        pod_dir_path = ASSERT.predicate(get_pod_dir_path(pod_id), Path.is_dir)
        config = read_config(pod_dir_path)
        pod_status = get_pod_status(pod_dir_path, config)
        return [{
            'name': app.name,
            'status': pod_status.get(app.name, (None, None))[0],
            'last-updated': pod_status.get(app.name, (None, None))[1],
        } for app in config.apps]


def cmd_cat_config(pod_id, output):
    config_path = ASSERT.predicate(
        get_config_path(get_pod_dir_path(pod_id)), Path.is_file
    )
    output.write(config_path.read_bytes())


def cmd_run(pod_id, config_path, *, debug=False):
    bases.assert_root_privilege()
    cmd_prepare(pod_id, config_path)
    run_pod(pod_id, debug=debug)


def cmd_prepare(pod_id, config_path):
    """Prepare a pod directory, or no-op if pod exists."""
    bases.assert_root_privilege()
    # Make sure that it is safe to create a pod with this ID.
    ASSERT.not_equal(pod_id_to_machine_id(pod_id), read_host_machine_id())
    # Check before really preparing the pod.
    if bases.lexists(get_pod_dir_path(pod_id)):
        LOG.info('skip duplicated pod: %s', pod_id)
        return
    config = bases.read_jsonobject(PodConfig, config_path)
    tmp_path = create_tmp_pod_dir()
    try:
        prepare_pod_dir(tmp_path, pod_id, config)
        with bases.acquiring_exclusive(get_active_path()):
            if maybe_move_pod_dir_to_active(tmp_path, pod_id):
                tmp_path = None
            else:
                LOG.info('skip duplicated pod: %s', pod_id)
    finally:
        if tmp_path:
            remove_pod_dir(tmp_path)


def cmd_run_prepared(pod_id, *, debug=False):
    bases.assert_root_privilege()
    pod_dir_path = ASSERT.predicate(get_pod_dir_path(pod_id), Path.is_dir)
    lock_pod_dir_for_exec(pod_dir_path)
    if bases.is_empty_dir(get_rootfs_path(pod_dir_path)):
        LOG.warning('overlay is not mounted; system probably rebooted')
        mount_overlay(pod_dir_path, read_config(pod_dir_path))
    run_pod(pod_id, debug=debug)


def cmd_remove(pod_id):
    """Remove a pod, or no-op if pod does not exist."""
    bases.assert_root_privilege()
    pod_dir_path = get_pod_dir_path(pod_id)
    with bases.acquiring_exclusive(get_active_path()):
        if not pod_dir_path.is_dir():
            LOG.debug('pod does not exist: %s', pod_id)
            return
        pod_dir_lock = bases.try_acquire_exclusive(pod_dir_path)
        if not pod_dir_lock:
            LOG.warning('pod is still active: %s', pod_id)
            return
    try:
        with bases.acquiring_exclusive(get_graveyard_path()):
            grave_path = move_pod_dir_to_graveyard(pod_dir_path)
        remove_pod_dir(grave_path)
    finally:
        pod_dir_lock.release()
        pod_dir_lock.close()


def cmd_cleanup(expiration):
    bases.assert_root_privilege()
    cleanup_active(expiration)
    for top_dir_path in (
        get_tmp_path(),
        get_graveyard_path(),
    ):
        with bases.acquiring_exclusive(top_dir_path):
            cleanup_top_dir(top_dir_path)


def cleanup_active(expiration):
    LOG.info('remove pods before: %s', expiration)
    with bases.acquiring_exclusive(get_active_path()):
        for pod_dir_path, config in iter_configs():
            pod_id = get_id(pod_dir_path)
            pod_dir_lock = bases.try_acquire_exclusive(pod_dir_path)
            if not pod_dir_lock:
                LOG.debug('pod is still active: %s', pod_id)
                continue
            try:
                pod_status = get_pod_status(pod_dir_path, config)
                last_updated = get_last_updated(pod_status)
                if last_updated is None:
                    # Prevent cleaning up just-prepared pod directory.
                    last_updated = datetimes.utcfromtimestamp(
                        get_config_path(pod_dir_path).stat().st_mtime
                    )
                if last_updated < expiration:
                    with bases.acquiring_exclusive(get_graveyard_path()):
                        LOG.info('clean up pod: %s', pod_id)
                        move_pod_dir_to_graveyard(pod_dir_path)
            finally:
                pod_dir_lock.release()
                pod_dir_lock.close()


#
# Locking strategy.
#


def create_tmp_pod_dir():
    """Create and then lock a temporary directory.

    NOTE: This lock is not released/close on exec.
    """
    tmp_dir_path = get_tmp_path()
    with bases.acquiring_exclusive(tmp_dir_path):
        tmp_path = Path(tempfile.mkdtemp(dir=tmp_dir_path))
        try:
            tmp_path.chmod(mode=0o750)
            bases.chown_app(tmp_path)
            lock_pod_dir_for_exec(tmp_path)
        except:
            tmp_path.rmdir()
            raise
        return tmp_path


def lock_pod_dir_for_exec(pod_dir_path):
    """Lock pod directory.

    NOTE: This lock is not released/close on exec.
    """
    pod_dir_lock = bases.FileLock(pod_dir_path, close_on_exec=False)
    pod_dir_lock.acquire_exclusive()


def is_pod_dir_locked(pod_dir_path):
    pod_dir_lock = bases.try_acquire_exclusive(pod_dir_path)
    if pod_dir_lock:
        pod_dir_lock.release()
        pod_dir_lock.close()
        return False
    else:
        return True


#
# Data type.
#


@dataclasses.dataclass(frozen=True)
class PodConfig:

    # Re-export ``App`` type.
    App = builders.App

    @dataclasses.dataclass(frozen=True)
    class Image:

        id: typing.Optional[str] = None
        name: typing.Optional[str] = None
        version: typing.Optional[str] = None
        tag: typing.Optional[str] = None

        def __post_init__(self):
            ASSERT.only_one((self.id, self.name or self.version, self.tag))
            ASSERT.not_xor(self.name, self.version)
            if self.id:
                images.validate_id(self.id)
            elif self.name:
                images.validate_name(self.name)
                images.validate_version(self.version)
            else:
                images.validate_tag(self.tag)

    @dataclasses.dataclass(frozen=True)
    class Volume:

        source: str
        target: str
        read_only: bool = True

        def __post_init__(self):
            ASSERT.predicate(Path(self.source), Path.is_absolute)
            ASSERT.predicate(Path(self.target), Path.is_absolute)

    name: str
    version: str
    apps: typing.List[App]
    # Image are ordered from low to high.
    images: typing.List[Image]
    volumes: typing.List[Volume] = ()

    def __post_init__(self):
        images.validate_name(self.name)
        images.validate_version(self.version)
        ASSERT.not_empty(self.apps)
        ASSERT.not_empty(self.images)
        ASSERT(
            len(set(u.name for u in self.apps)) == len(self.apps),
            'expect unique app names: {}',
            self.apps,
        )
        ASSERT(
            len(set(v.target for v in self.volumes)) == len(self.volumes),
            'expect unique volume targets: {}',
            self.volumes,
        )


UUID_PATTERN = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
)


def generate_id():
    return validate_id(str(uuid.uuid4()))


def validate_id(pod_id):
    return ASSERT.predicate(pod_id, UUID_PATTERN.fullmatch)


#
# Repo layout.
#

PODS = 'pods'

ACTIVE = 'active'
GRAVEYARD = 'graveyard'
TMP = 'tmp'

# Entries in a pod directory.
CONFIG = 'config'
DEPS = 'deps'
WORK = 'work'
UPPER = 'upper'
ROOTFS = 'rootfs'


def get_pod_repo_path():
    return bases.get_repo_path() / PODS


def get_active_path():
    return get_pod_repo_path() / ACTIVE


def get_graveyard_path():
    return get_pod_repo_path() / GRAVEYARD


def get_tmp_path():
    return get_pod_repo_path() / TMP


def get_pod_dir_path(pod_id):
    return get_active_path() / validate_id(pod_id)


def get_id(pod_dir_path):
    return validate_id(pod_dir_path.name)


def get_config_path(pod_dir_path):
    return pod_dir_path / CONFIG


def get_deps_path(pod_dir_path):
    return pod_dir_path / DEPS


def get_work_path(pod_dir_path):
    return pod_dir_path / WORK


def get_upper_path(pod_dir_path):
    return pod_dir_path / UPPER


def get_rootfs_path(pod_dir_path):
    return pod_dir_path / ROOTFS


#
# Functions below require caller acquiring locks.
#

#
# Top-level directories.
#


def cleanup_top_dir(top_dir_path):
    for path in top_dir_path.iterdir():
        if not path.is_dir():
            LOG.info('remove unknown file: %s', path)
            path.unlink()
            continue
        lock = bases.try_acquire_exclusive(path)
        if not lock:
            continue
        try:
            remove_pod_dir(path)
        finally:
            lock.release()
            lock.close()


#
# Pod directories.
#


def iter_pod_dir_paths():
    for pod_dir_path in get_active_path().iterdir():
        if not pod_dir_path.is_dir():
            LOG.debug('encounter unknown file under active: %s', pod_dir_path)
        else:
            yield pod_dir_path


def maybe_move_pod_dir_to_active(dir_path, pod_id):
    pod_dir_path = get_pod_dir_path(pod_id)
    if bases.lexists(pod_dir_path):
        return False
    else:
        dir_path.rename(pod_dir_path)
        return True


def move_pod_dir_to_graveyard(dir_path):
    dst_path = get_graveyard_path() / dir_path.name
    if bases.lexists(dst_path):
        dst_path.with_name('%s_%s' % (dst_path.name, generate_id()))
        LOG.debug(
            'rename duplicated pod directory under graveyard: %s -> %s',
            dir_path.name,
            dst_path.name,
        )
        ASSERT.not_predicate(dst_path, bases.lexists)
    dir_path.rename(dst_path)
    return dst_path


#
# Pod directory.
#


def prepare_pod_dir(pod_dir_path, pod_id, config):
    LOG.info('prepare pod: %s', pod_id)
    setup_pod_dir_barely(pod_dir_path, config)
    add_ref_image_ids(pod_dir_path, config)
    mount_overlay(pod_dir_path, config)
    rootfs_path = get_rootfs_path(pod_dir_path)
    builders.generate_machine_id(rootfs_path, pod_id_to_machine_id(pod_id))
    generate_hostname(rootfs_path, pod_id)
    generate_unit_files(rootfs_path, config)


def setup_pod_dir_barely(pod_dir_path, config):
    write_config(config, pod_dir_path)
    for path in (
        get_deps_path(pod_dir_path),
        get_work_path(pod_dir_path),
        get_upper_path(pod_dir_path),
        get_rootfs_path(pod_dir_path),
    ):
        path.mkdir()
    for path, mode, chown in (
        (get_config_path(pod_dir_path), 0o640, bases.chown_app),
        (get_deps_path(pod_dir_path), 0o750, bases.chown_app),
        # Trivia: After overlay is mounted, root directory's mode is
        # actaully the same as upper's.
        (get_work_path(pod_dir_path), 0o755, bases.chown_root),
        (get_upper_path(pod_dir_path), 0o755, bases.chown_root),
        (get_rootfs_path(pod_dir_path), 0o755, bases.chown_root),
    ):
        path.chmod(mode)
        chown(path)


def remove_pod_dir(pod_dir_path):
    LOG.info('remove pod directory: %s', pod_dir_path)
    umount_overlay(pod_dir_path)
    with bases.acquiring_shared(images.get_trees_path()):
        for ref_image_id in iter_ref_image_ids(pod_dir_path):
            images.touch(ref_image_id)
    shutil.rmtree(pod_dir_path)


#
# Pod.
#


def mount_overlay(pod_dir_path, config):
    rootfs_path = get_rootfs_path(pod_dir_path)
    LOG.info('mount overlay: %s', rootfs_path)
    #
    # Since we should have added image refs, it is safe to access image
    # directories without locking them.
    #
    # NOTE: You cannot use iter_ref_image_ids here as its result is not
    # ordered; you must use iter_image_ids.
    #
    image_ids = list(iter_image_ids(config))
    base_image_name, base_image_version = ASSERT.not_equal(
        images.find_name_and_version(image_id=image_ids[0]),
        (None, None),
    )
    if base_image_name != bases.PARAMS.base_image_name.get():
        LOG.warning('expect base image at the lowest, not %s', base_image_name)
    if base_image_version != bases.PARAMS.base_image_version.get():
        LOG.warning(
            'expect base image version %s, not %s',
            bases.PARAMS.base_image_version.get(),
            base_image_version,
        )
    # Call reverse() because in overlay file system, lower directories
    # are ordered from high to low.
    image_ids.reverse()
    subprocess.run(
        [
            'mount',
            '-t',
            'overlay',
            '-o',
            'lowerdir=%s,upperdir=%s,workdir=%s' % (
                ':'.join(
                    str(get_image_rootfs_path(image_id))
                    for image_id in image_ids
                ),
                get_upper_path(pod_dir_path),
                get_work_path(pod_dir_path),
            ),
            'overlay',
            str(rootfs_path),
        ],
        check=True,
    )


def umount_overlay(pod_dir_path):
    rootfs_path = get_rootfs_path(pod_dir_path)
    umount(rootfs_path)
    # Just a sanity check that rootfs is really unmounted.
    ASSERT.predicate(rootfs_path, bases.is_empty_dir)


def generate_hostname(rootfs_path, pod_id):
    hostname = make_hostname(pod_id)
    (rootfs_path / 'etc/hostname').write_text(hostname + '\n')
    (rootfs_path / 'etc/hosts').write_text(
        '127.0.0.1\tlocalhost\n'
        '127.0.1.1\t%s\n' % hostname
    )


def generate_unit_files(rootfs_path, config):
    for app in config.apps:
        builders.generate_unit_file(
            rootfs_path, config.name, config.version, app
        )


def run_pod(pod_id, *, debug=False):
    LOG.info('start pod: %s', pod_id)
    pod_dir_path = ASSERT.predicate(get_pod_dir_path(pod_id), Path.is_dir)
    rootfs_path = get_rootfs_path(pod_dir_path)
    config = read_config(pod_dir_path)
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
        '--machine=%s' % make_hostname(pod_id),
        '--register=yes',
        *(['--keep-unit'] if is_running_from_system_service() else []),
        '--boot',
        '--directory=%s' % rootfs_path,
        *(make_bind_argument(volume) for volume in config.volumes),
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
    LOG.debug('run_pod: args=%s', args)
    os.execvp(args[0], args)
    ASSERT.unreachable('unable to start pod: {}', pod_id)


def make_hostname(pod_id):
    return 'ctr-%s' % pod_id


def make_bind_argument(volume):
    return '--bind%s=%s:%s' % (
        '-ro' if volume.read_only else '',
        ASSERT.not_contains(volume.source, ':'),
        ASSERT.not_contains(volume.target, ':'),
    )


#
# Configs.
#


def iter_configs():
    for pod_dir_path in iter_pod_dir_paths():
        yield pod_dir_path, read_config(pod_dir_path)


def read_config(pod_dir_path):
    return bases.read_jsonobject(PodConfig, get_config_path(pod_dir_path))


def write_config(config, pod_dir_path):
    bases.write_jsonobject(config, get_config_path(pod_dir_path))


def iter_image_ids(config):
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
# Dependent images.
#


def add_ref_image_ids(pod_dir_path, config):
    deps_path = get_deps_path(pod_dir_path)
    with bases.acquiring_shared(images.get_trees_path()):
        for image_id in iter_image_ids(config):
            images.add_ref(image_id, deps_path / image_id)


def iter_ref_image_ids(pod_dir_path):
    """Iterate over ref image IDs.

    NOTE: The results are not ordered.
    """
    for ref_path in get_deps_path(pod_dir_path).iterdir():
        if not ref_path.is_file():
            LOG.debug('encounter unknown file under deps: %s', ref_path)
        else:
            yield images.validate_id(ref_path.name)


def get_image_rootfs_path(image_id):
    return images.get_rootfs_path(images.get_image_dir_path(image_id))


#
# Pod runtime state.
#


def get_pod_status(pod_dir_path, config):
    rootfs_path = get_rootfs_path(pod_dir_path)
    pod_status = {}
    for app in config.apps:
        status, mtime = builders.get_pod_app_exit_status(rootfs_path, app)
        if status is not None:
            pod_status[app.name] = (status, mtime)
    return pod_status


def get_last_updated(pod_status):
    """Return the most recent last-updated."""
    return max((mtime for _, mtime in pod_status.values()), default=None)


#
# Helpers for mount/umount.
#

UMOUNT_ERROR_WHITELIST = re.compile(br': not mounted\.$')


def umount(path):
    ASSERT.not_predicate(path, Path.is_symlink)
    LOG.info('umount: %s', path)
    try:
        subprocess.run(['umount', str(path)], check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        if UMOUNT_ERROR_WHITELIST.search(exc.stderr, re.MULTILINE):
            LOG.debug('umount err: %s, %s', path, exc.stderr, exc_info=True)
        else:
            LOG.error('umount err: %s, %s', path, exc.stderr)
            raise


#
# Host system.
#


def pod_id_to_machine_id(pod_id):
    return pod_id.replace('-', '')


def read_host_machine_id():
    return Path('/etc/machine-id').read_text().strip()


def is_running_from_system_service():
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