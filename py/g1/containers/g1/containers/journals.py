"""Manage systemd journals."""

__all__ = [
    'remove_journal_dir',
]

import logging
from pathlib import Path

import g1.files

from . import models

LOG = logging.getLogger(__name__)

_JOURNAL_BASE_DIR_PATH = Path('/var/log/journal')


def _get_journal_dir_path(pod_id):
    return (
        _JOURNAL_BASE_DIR_PATH /
        models.pod_id_to_machine_id(models.validate_pod_id(pod_id))
    )


def remove_journal_dir(pod_id):
    path = _get_journal_dir_path(pod_id)
    LOG.info('remove journal directory: %s', path)
    g1.files.remove(path)
