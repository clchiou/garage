"""Helpers for scripting ctr."""

__all__ = [
    'ctr',
    # Pod commands.
    'ctr_add_ref_to_pod',
    'ctr_prepare_pod',
    'ctr_remove_pod',
    'ctr_run_pod',
    'ctr_run_prepared_pod',
    # XAR commands.
    'ctr_install_xar',
    'ctr_uninstall_xar',
    # Image commands.
    'ctr_build_image',
    'ctr_get_image_rootfs_path',
    'ctr_import_image',
    'ctr_remove_image',
]

import csv
import logging

from g1 import scripts
from g1.bases.assertions import ASSERT

_VERBOSE = None


def ctr(args):
    global _VERBOSE
    if _VERBOSE is None:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            _VERBOSE = ('--verbose', )
        else:
            _VERBOSE = ()
    return scripts.run(['ctr', *_VERBOSE, *args])


def ctr_prepare_pod(pod_id, config_path):
    return ctr(['pods', 'prepare', '--id', pod_id, config_path])


def ctr_run_prepared_pod(pod_id):
    return ctr(['pods', 'run-prepared', pod_id])


def ctr_run_pod(pod_id, config_path):
    return ctr(['pods', 'run', '--id', pod_id, config_path])


def ctr_add_ref_to_pod(pod_id, target_path):
    return ctr(['pods', 'add-ref', pod_id, target_path])


def ctr_remove_pod(pod_id):
    return ctr(['pods', 'remove', pod_id])


def ctr_install_xar(name, exec_relpath, image):
    return ctr(['xars', 'install', *_image_to_args(image), name, exec_relpath])


def ctr_uninstall_xar(name):
    return ctr(['xars', 'uninstall', name])


def ctr_build_image(name, version, rootfs_path, image_path):
    return ctr([
        'images',
        'build',
        *('--rootfs', rootfs_path),
        name,
        version,
        image_path,
    ])


def ctr_import_image(image_path):
    return ctr(['images', 'import', image_path])


def ctr_remove_image(image):
    return ctr(['images', 'remove', *_image_to_args(image)])


def ctr_get_image_rootfs_path(image):
    if image.id is not None:
        match = lambda row: row[0] == image.id
    elif image.name is not None and image.version is not None:
        match = lambda row: row[1] == image.name and row[2] == image.version
    else:
        ASSERT.not_none(image.tag)
        match = lambda row: image.tag in row[3].split(' ')
    with scripts.doing_capture_output():
        proc = ctr([
            'images',
            'list',
            *('--format', 'csv'),
            *('--columns', 'id,name,version,tags,rootfs'),
        ])
        for row in csv.reader(proc.stdout.decode('utf8').split('\n')):
            if match(row):
                return row[4]
    return ASSERT.unreachable('cannot find image: {}', image)


def _image_to_args(image):
    if image.id is not None:
        return ('--id', image.id)
    elif image.name is not None and image.version is not None:
        return ('--nv', image.name, image.version)
    else:
        ASSERT.not_none(image.tag)
        return ('--tag', image.tag)
