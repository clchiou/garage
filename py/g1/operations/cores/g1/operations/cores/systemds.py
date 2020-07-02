__all__ = [
    # Environment variables.
    'make_envs',
    # Unit file manipulators.
    'install',
    'uninstall',
    # systemctl wrappers.
    'activate',
    'daemon_reload',
    'deactivate',
    'is_active',
    'is_enabled',
]

import logging
import shutil

import g1.files
from g1 import scripts
from g1.bases.assertions import ASSERT

from . import models

LOG = logging.getLogger(__name__)


def make_envs(pod_id, pod_metadata, *envs_list):
    merged_envs = {
        ('%s_id' % models.ENV_PREFIX): pod_id,
        ('%s_label' % models.ENV_PREFIX): pod_metadata.label,
        ('%s_version' % models.ENV_PREFIX): pod_metadata.version,
    }
    for envs in envs_list:
        for k, v in envs.items():
            # Forbid overwriting env entries.
            ASSERT.setitem(merged_envs, k, v)
    return merged_envs


def install(config, pod_metadata, group, unit, *envs_list):
    _make_unit_file(unit.content, config.unit_path)
    _make_unit_config_file(
        make_envs(config.pod_id, pod_metadata, group.envs, *envs_list),
        config.unit_config_path,
    )
    return True


def uninstall(config):
    g1.files.remove(config.unit_path)
    g1.files.remove(config.unit_config_path.parent)
    return True


def _make_unit_file(content, unit_path):
    LOG.info('create unit file: %s', unit_path)
    unit_path.write_text(content)
    unit_path.chmod(0o644)
    shutil.chown(unit_path, 'root', 'root')


def _make_unit_config_file(envs, unit_config_path):
    dropin_dir_path = unit_config_path.parent
    LOG.info('create drop-in directory: %s', dropin_dir_path)
    dropin_dir_path.mkdir(mode=0o755, parents=False, exist_ok=True)
    # Just in case drop_in_path is already created.
    dropin_dir_path.chmod(0o755)
    shutil.chown(dropin_dir_path, 'root', 'root')
    LOG.info('create unit config file: %s', unit_config_path)
    with unit_config_path.open('w') as config_file:
        config_file.write('[Service]\n')
        for k, v in envs.items():
            config_file.write('Environment="%s=%s"\n' % (k, v))
    unit_config_path.chmod(0o644)
    shutil.chown(unit_config_path, 'root', 'root')


def activate(config):
    LOG.info('activate unit: %s %s', config.pod_id, config.name)
    # "--now" implies "start".
    systemctl(['--now', 'enable', config.unit_name])
    ASSERT.true(is_enabled(config))
    ASSERT.true(is_active(config))


def deactivate(config):
    LOG.info('deactivate unit: %s %s', config.pod_id, config.name)
    # "--now" implies "stop".
    systemctl(['--now', 'disable', config.unit_name])
    ASSERT.false(is_enabled(config))
    ASSERT.false(is_active(config))


def is_enabled(config):
    with scripts.doing_check(False):
        proc = systemctl(['--quiet', 'is-enabled', config.unit_name])
        return proc.returncode == 0


def is_active(config):
    with scripts.doing_check(False):
        proc = systemctl(['--quiet', 'is-active', config.unit_name])
        return proc.returncode == 0


def daemon_reload():
    return systemctl(['daemon-reload'])


def systemctl(args):
    return scripts.run(['systemctl', '--no-ask-password', *args])
