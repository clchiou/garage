"""Build base image and pod runtime.

The construction of a pod is divided into two phases:

* Base image construction: This sets up the basic environment of a pod.
  Notably, /usr/sbin/pod-exit and /var/lib/pod/exit-status.

* Pod runtime: This includes systemd unit files and exit status.
"""

__all__ = [
    # Expose to apps.
    'cmd_build_base_image',
    'cmd_init',
    'cmd_prepare_base_rootfs',
    'cmd_setup_base_rootfs',
    # Expose to pods.
    'clear_pod_app_exit_status',
    'generate_machine_id',
    'generate_unit_file',
    'get_pod_app_exit_status',
]

import dataclasses
import enum
import logging
import re
from pathlib import Path

import g1.files
from g1 import scripts
from g1.bases import argparses
from g1.bases import datetimes
from g1.bases import oses
from g1.bases.assertions import ASSERT

from . import bases
from . import images
from . import models

LOG = logging.getLogger(__name__)


def cmd_init():
    scripts.check_command_exist('debootstrap')


#
# Base image.
#


@argparses.begin_parser(
    'build-base', **argparses.make_help_kwargs('build a base image')
)
@argparses.argument(
    '--prune-stash-path',
    metavar='PATH',
    type=Path,
    help='provide path to stash pruned files',
)
@images.image_output_arguments
@argparses.end
def cmd_build_base_image(name, version, base_image_path, prune_stash_path):
    oses.assert_root_privilege()
    LOG.info('create base image: %s', base_image_path)
    images.build_image(
        images.ImageMetadata(name=name, version=version),
        lambda dst_path: _create_image_rootfs(dst_path, prune_stash_path),
        base_image_path,
    )


def _create_image_rootfs(image_rootfs_path, prune_stash_path):
    cmd_prepare_base_rootfs(image_rootfs_path)
    cmd_setup_base_rootfs(image_rootfs_path, prune_stash_path)


@argparses.begin_parser(
    'prepare-base-rootfs',
    **argparses.make_help_kwargs(
        'prepare rootfs of a base image (useful for testing)',
    ),
)
@argparses.argument('path', type=Path, help='provide rootfs directory path')
@argparses.end
def cmd_prepare_base_rootfs(image_rootfs_path):
    ASSERT.not_predicate(image_rootfs_path, Path.exists)
    oses.assert_root_privilege()
    scripts.run([
        'debootstrap',
        '--variant=minbase',
        '--components=main',
        # Install dbus for convenience.
        # Install sudo for changing service user/group.
        # Install tzdata for /etc/localtime.
        '--include=dbus,sudo,systemd,tzdata',
        models.BASE_IMAGE_RELEASE_CODE_NAME,
        image_rootfs_path,
        'http://us.archive.ubuntu.com/ubuntu/',
    ])


@argparses.begin_parser(
    'setup-base-rootfs',
    **argparses.make_help_kwargs(
        'set up rootfs of a base image (useful for testing)',
    ),
)
@argparses.argument(
    '--prune-stash-path',
    metavar='PATH',
    type=Path,
    help='provide path to stash pruned files',
)
@argparses.argument('path', type=Path, help='provide rootfs directory path')
@argparses.end
def cmd_setup_base_rootfs(image_rootfs_path, prune_stash_path):
    """Set up base rootfs.

    Changes from 18.04 to 20.04.
    * /lib is now a symlink to /usr/lib.
    * system.slice has been removed:
      https://github.com/systemd/systemd/commit/d8e5a9338278d6602a0c552f01f298771a384798
    """
    ASSERT.predicate(image_rootfs_path, Path.is_dir)
    oses.assert_root_privilege()

    _cleanup_unneeded_files(image_rootfs_path, prune_stash_path)
    _remove_config_files(image_rootfs_path)
    _replace_config_files(image_rootfs_path)
    _setup_unit_files(image_rootfs_path)
    _setup_pod_exit(image_rootfs_path)

def _cleanup_unneeded_files(image_rootfs_path, prune_stash_path):
    for dir_relpath in (
        'usr/share/doc',
        'usr/share/info',
        'usr/share/man',
        'var/cache',
        'var/lib/apt',
        'var/lib/dpkg',
    ):
        dir_path = image_rootfs_path / dir_relpath
        if dir_path.is_dir():
            if prune_stash_path:
                dst_path = ASSERT.not_predicate(
                    prune_stash_path / dir_relpath, g1.files.lexists
                )
                dst_path.mkdir(mode=0o755, parents=True, exist_ok=True)
                _move_dir_content(dir_path, dst_path)
            else:
                _clear_dir_content(dir_path)

def _remove_config_files(image_rootfs_path):
    for path in (
        image_rootfs_path / 'etc/hostname',
        image_rootfs_path / 'etc/machine-id',
        image_rootfs_path / 'var/lib/dbus/machine-id',
        image_rootfs_path / 'etc/resolv.conf',
        image_rootfs_path / 'run/systemd/resolve/stub-resolv.conf',
    ):
        LOG.info('remove: %s', path)
        g1.files.remove(path)

def _replace_config_files(image_rootfs_path):
    for path, content in (
        (image_rootfs_path / 'etc/default/locale', _LOCALE),
        (image_rootfs_path / 'etc/resolv.conf', _RESOLV_CONF),
        (image_rootfs_path / 'etc/systemd/journald.conf', _JOURNALD_CONF),
    ):
        LOG.info('replace: %s', path)
        path.write_text(content)

def _setup_unit_files(image_rootfs_path):
    base_units = set(_BASE_UNITS)
    for unit_dir_path in (
        image_rootfs_path / 'etc/systemd/system',
        image_rootfs_path / 'usr/lib/systemd/system',
    ):
        if not unit_dir_path.exists():
            continue
        _cleanup_unit_files(unit_dir_path, base_units)
    ASSERT.empty(base_units)

    _create_unit_files(image_rootfs_path)

def _cleanup_unit_files(unit_dir_path, base_units):
    LOG.info('clean up unit files in: %s', unit_dir_path)
    for unit_path in unit_dir_path.iterdir():
        if unit_path.name in base_units:
            base_units.remove(unit_path.name)
            continue
        ASSERT.not_in(unit_path.name, _BASE_UNITS)
        LOG.info('remove: %s', unit_path)
        g1.files.remove(unit_path)

def _create_unit_files(image_rootfs_path):
    for unit_dir_path, unit_files in (
        (image_rootfs_path / 'etc/systemd/system', _ETC_UNIT_FILES),
        (image_rootfs_path / 'usr/lib/systemd/system', _LIB_UNIT_FILES),
    ):
        for unit_file in unit_files:
            ASSERT.predicate(unit_dir_path, Path.is_dir)
            path = unit_dir_path / unit_file.relpath
            LOG.info('create: %s', path)
            _create_unit_file(path, unit_file)

def _create_unit_file(path, unit_file):
    if unit_file.kind is _UnitFile.Kinds.DIRECTORY:
        path.mkdir(mode=0o755)
    elif unit_file.kind is _UnitFile.Kinds.FILE:
        path.write_text(unit_file.content)
        path.chmod(0o644)
    else:
        ASSERT.is_(unit_file.kind, _UnitFile.Kinds.SYMLINK)
        path.symlink_to(unit_file.content)
    bases.chown_root(path)

def _setup_pod_exit(image_rootfs_path):
    pod_exit_path = image_rootfs_path / 'usr/sbin/pod-exit'
    LOG.info('create: %s', pod_exit_path)
    pod_exit_path.write_text(_POD_EXIT)
    bases.setup_file(pod_exit_path, 0o755, bases.chown_root)
    bases.make_dir(image_rootfs_path / 'var/lib/pod', 0o755, bases.chown_root)
    bases.make_dir(
        image_rootfs_path / 'var/lib/pod/exit-status', 0o755, bases.chown_root
    )


#
# Pod runtime.
#


def _get_pod_etc_path(root_path):
    return root_path / 'etc/systemd/system'


def _get_pod_unit_path(pod_etc_path, app):
    return pod_etc_path / _get_pod_unit_filename(app)


def _get_pod_unit_filename(app):
    return app.name + '.service'


def _get_pod_wants_path(pod_etc_path, app):
    return pod_etc_path / 'pod.target.wants' / _get_pod_unit_filename(app)


def _get_pod_app_exit_status_dir_path(root_path):
    return root_path / 'var/lib/pod/exit-status'


def _get_pod_app_exit_status_path(root_path, app):
    return (
        _get_pod_app_exit_status_dir_path(root_path) /
        _get_pod_unit_filename(app)
    )


def generate_machine_id(root_path, machine_id):
    machine_id_str = machine_id + '\n'
    for path, mode in (
        (root_path / 'etc/machine-id', 0o444),
        (root_path / 'var/lib/dbus/machine-id', 0o644),
    ):
        path.write_text(machine_id_str)
        bases.setup_file(path, mode, bases.chown_root)


def generate_unit_file(root_path, pod_name, pod_version, app):
    LOG.info('create unit file: %s', app.name)
    pod_etc_path = ASSERT.predicate(_get_pod_etc_path(root_path), Path.is_dir)
    ASSERT.not_predicate(
        _get_pod_unit_path(pod_etc_path, app),
        g1.files.lexists,
    ).write_text(_generate_unit_file_content(pod_name, pod_version, app))
    ASSERT.not_predicate(
        _get_pod_wants_path(pod_etc_path, app),
        g1.files.lexists,
    ).symlink_to(Path('..') / _get_pod_unit_filename(app))


def _generate_unit_file_content(pod_name, pod_version, app):
    if app.service_section is None:
        if app.user != 'root' or app.group != 'root':
            # Use ``sudo`` rather than "User=" and "Group=", or else
            # "ExecStart" command will not be able to connect to journal
            # socket, and pod-exit at "ExecStopPost" does not have the
            # permission to stop the pod.
            exec_start = [
                '/usr/bin/sudo',
                '--user=%s' % app.user,
                '--group=%s' % app.group,
            ]
            exec_start.extend(app.exec)
        else:
            exec_start = app.exec
        # TODO: The default limit 1024 is too small for some server
        # applications; we increase LimitNOFILE to 65536.  But consider
        # make it configurable.
        service_section = '''\
{service_type}\
Restart=no
SyslogIdentifier={pod_name}/{app.name}@{pod_version}
ExecStart={exec}
ExecStopPost=/usr/sbin/pod-exit "%n"
{kill_mode}\
LimitNOFILE=65536'''.format(
            app=app,
            exec=' '.join(map(_quote_arg, exec_start)),
            kill_mode=(
                '' if app.kill_mode is None else \
                'KillMode=%s\n' % app.kill_mode
            ),
            pod_name=pod_name,
            pod_version=pod_version,
            service_type=(
                'Type=%s\n' % app.type if app.type is not None else ''
            ),
        )
    else:
        service_section = app.service_section
    return '''\
[Unit]
After=pod.target

[Service]
{service_section}
'''.format(service_section=service_section)


_ESCAPE_PATTERN = re.compile(r'[\'"$%]')
_ESCAPE_MAP = {
    '\'': '\\\'',
    '"': '\\"',
    '$': '$$',
    '%': '%%',
}


def _quote_arg(arg):
    return '"%s"' % _ESCAPE_PATTERN.sub(
        lambda match: _ESCAPE_MAP[match.group(0)],
        # TODO: Handle '\' escape sequence.
        ASSERT.not_contains(arg, '\\'),
    )


def clear_pod_app_exit_status(root_path):
    _clear_dir_content(_get_pod_app_exit_status_dir_path(root_path))


def get_pod_app_exit_status(root_path, app):
    """Return exit status and the time it was recorded."""
    path = _get_pod_app_exit_status_path(root_path, app)
    if path.is_file():
        return (
            int(path.read_text()),
            datetimes.utcfromtimestamp(path.stat().st_mtime),
        )
    else:
        return None, None


def _clear_dir_content(dir_path):
    LOG.info('clear directory content: %s', dir_path)
    for path in dir_path.iterdir():
        g1.files.remove(path)


def _move_dir_content(src_path, dst_path):
    LOG.info('move directory content: %s -> %s', src_path, dst_path)
    for path in src_path.iterdir():
        path.rename(dst_path / path.name)


#
# Base rootfs config data.
#

# Keep these unit files of the base image.
_BASE_UNITS = frozenset((
    'ctrl-alt-del.target',
    # D-Bus.  With it we may ``machinectl shell`` into containers, which
    # is probably bad for security, but is quite convenient.
    'dbus.service',
    'dbus.socket',
    # Journal.
    'systemd-journald-audit.socket',
    'systemd-journald-dev-log.socket',
    'systemd-journald.service',
    'systemd-journald.socket',
    'systemd-journal-flush.service',
    # Slices.
    'machine.slice',
    'slices.target',
    'user.slice',
    # tmpfiles.
    'systemd-tmpfiles-setup-dev.service',
    'systemd-tmpfiles-setup.service',
))


@dataclasses.dataclass(frozen=True)
class _UnitFile:
    """Descriptor of systemd unit file of base image."""

    class Kinds(enum.Enum):
        DIRECTORY = enum.auto()
        FILE = enum.auto()
        SYMLINK = enum.auto()

    relpath: str
    kind: Kinds
    content: str

    @classmethod
    def make_dir(cls, relpath):
        return cls(
            relpath=relpath, kind=_UnitFile.Kinds.DIRECTORY, content=None
        )

    @classmethod
    def make_file(cls, relpath, content):
        return cls(relpath=relpath, kind=_UnitFile.Kinds.FILE, content=content)

    @classmethod
    def make_symlink(cls, relpath, content):
        return cls(
            relpath=relpath, kind=_UnitFile.Kinds.SYMLINK, content=content
        )


_LOCALE = 'LANG="en_US.UTF-8"\n'
_RESOLV_CONF = 'nameserver 8.8.8.8\n'
_JOURNALD_CONF = '''\
[Journal]
SystemMaxUse=64M
RuntimeMaxUse=64M
'''

# Add these unit files to the base image.
_ETC_UNIT_FILES = (
    # Apps should make pod.target "wants" them.
    _UnitFile.make_dir('pod.target.wants'),
)
_LIB_UNIT_FILES = (
    # NOTE: Unit files must not be empty, or else systemd will treat
    # them as masked.
    #
    # sysinit.target.
    _UnitFile.make_file('sysinit.target', '[Unit]\n'),
    _UnitFile.make_dir('sysinit.target.wants'),
    *(
        _UnitFile.make_symlink(
            'sysinit.target.wants/' + unit_name,
            '../' + unit_name,
        ) for unit_name in (
            'dbus.service',
            'systemd-journald.service',
            'systemd-journal-flush.service',
            'systemd-tmpfiles-setup-dev.service',
            'systemd-tmpfiles-setup.service',
        )
    ),
    # sockets.target.
    _UnitFile.make_file('sockets.target', '[Unit]\n'),
    _UnitFile.make_dir('sockets.target.wants'),
    *(
        _UnitFile.make_symlink(
            'sockets.target.wants/' + unit_name,
            '../' + unit_name,
        ) for unit_name in (
            'dbus.socket',
            'systemd-journald-audit.socket',
            'systemd-journald-dev-log.socket',
            'systemd-journald.socket',
        )
    ),
    # basic.target.
    _UnitFile.make_file(
        'basic.target', '''\
[Unit]
Requires=sysinit.target
Wants=sockets.target slices.target
After=sysinit.target sockets.target slices.target
'''
    ),
    # pod.target.
    _UnitFile.make_file(
        'pod.target', '''\
[Unit]
Requires=basic.target
After=basic.target
'''
    ),
    _UnitFile.make_symlink('default.target', 'pod.target'),
    # shutdown.target.
    _UnitFile.make_file(
        'shutdown.target', '''\
[Unit]
DefaultDependencies=no
RefuseManualStart=yes
'''
    ),
    # exit.target.
    _UnitFile.make_file(
        'exit.target', '''\
[Unit]
DefaultDependencies=no
Requires=systemd-exit.service
After=systemd-exit.service
AllowIsolate=yes
'''
    ),
    _UnitFile.make_file(
        'systemd-exit.service', '''\
[Unit]
DefaultDependencies=no
Requires=shutdown.target
After=shutdown.target

[Service]
Type=oneshot
ExecStart=/bin/systemctl --force exit
'''
    ),
    _UnitFile.make_symlink('halt.target', 'exit.target'),
    _UnitFile.make_symlink('poweroff.target', 'exit.target'),
    _UnitFile.make_symlink('reboot.target', 'exit.target'),
)

_POD_EXIT = '''#!/usr/bin/env bash

set -o errexit -o nounset -o pipefail

if [[ "${#}" -ne 1 ]]; then
  systemctl exit 1
  exit 1
fi

# Check whether there is already any status file.
has_status="$(ls -A /var/lib/pod/exit-status)"

status="$(systemctl show --property ExecMainStatus "${1}")"
status="${status#*=}"
status="${status:-1}"

echo "${status}" > "/var/lib/pod/exit-status/${1}"

# Check whether this is the first non-zero status.
if [[ "${status}" != 0 && -z "${has_status}" ]]; then
  systemctl exit "${status}"
else
  systemctl exit
fi
'''
