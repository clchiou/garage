"""Helpers for scripting ctr."""

__all__ = [
    'ctr',
    # Pod commands.
    'ctr_prepare_pod',
    'ctr_remove_pod',
    'ctr_run_pod',
    'ctr_run_prepared_pod',
    # XAR commands.
    'ctr_install_xar',
    # Image commands.
    'ctr_build_image',
    'ctr_get_image_rootfs_path',
    'ctr_import_image',
]

import csv
import logging
import shutil

from g1 import scripts
from g1.bases.assertions import ASSERT

# Look up `ctr` because sudo does not search into custom paths.
_CTR = None
_VERBOSE = None


def ctr(args):
    global _CTR, _VERBOSE
    if _CTR is None:
        _CTR = ASSERT.not_none(shutil.which('ctr'))
    if _VERBOSE is None:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            _VERBOSE = ('--verbose', )
        else:
            _VERBOSE = ()
    with scripts.using_sudo():
        return scripts.run([_CTR, *_VERBOSE, *args])


def ctr_prepare_pod(pod_id, config_path):
    return ctr(['pods', 'prepare', '--id', pod_id, config_path])


def ctr_run_prepared_pod(pod_id):
    return ctr(['pods', 'run-prepared', pod_id])


def ctr_run_pod(pod_id, config_path):
    return ctr(['pods', 'run', '--id', pod_id, config_path])


def ctr_remove_pod(pod_id):
    return ctr(['pods', 'remove', pod_id])


def ctr_install_xar(name, exec_relpath, image):
    if image.id is not None:
        image_args = ('--id', image.id)
    elif image.name is not None and image.version is not None:
        image_args = ('--nv', image.name, image.version)
    else:
        ASSERT.not_none(image.tag)
        image_args = ('--tag', image.tag)
    return ctr(['xars', 'install', *image_args, name, exec_relpath])


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


def ctr_get_image_rootfs_path(kind, args):
    if kind == 'id':
        match = lambda row: row[0] == args[0]
    elif kind == 'nv':
        match = lambda row: row[1:3] == list(args)
    elif kind == 'tag':
        match = lambda row: args[0] in row[3]
    else:
        return ASSERT.unreachable('unknown kind: {} {}', kind, args)
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
    return ASSERT.unreachable('cannot find image: {} {}', kind, args)
