"""Manage environment variables.

Note that, like tokens, environment variables are only substituted
during pod creation.  Changes to environment variables do not propagate
to existing pods.

Variable values can only be str-typed.
"""

__all__ = [
    'init',
    'load',
    'save',
]

import json
import logging

from . import bases
from . import models

LOG = logging.getLogger(__name__)

_ENVS_FILENAME = 'envs'


def init():
    envs_path = _get_envs_path()
    bases.make_dir(envs_path.parent)
    if envs_path.exists():
        LOG.info('skip: envs init: %s', envs_path)
        return
    LOG.info('envs init: %s', envs_path)
    save({})
    bases.set_file_attrs(envs_path)


def load():
    return json.loads(_get_envs_path().read_bytes())


def save(envs):
    _get_envs_path().write_text(json.dumps(envs), encoding='ascii')


def _get_envs_path():
    return bases.get_repo_path() / models.REPO_ENVS_DIR_NAME / _ENVS_FILENAME
