__all__ = [
    'get_builder_name',
    'get_builder_image_path',
    'get_image_path',
    'parse_images_parameter',
    # Helper commands.
    'chown',
    'rsync',
]

import getpass
import grp
import pwd

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT
from g1.containers import models

import shipyard2


def get_builder_name(name):
    return name + '-builder'


def get_builder_image_path(parameters, name):
    return get_image_path(parameters, name).with_name(
        shipyard2.IMAGE_DIR_BUILDER_IMAGE_FILENAME
    )


def get_image_path(parameters, name):
    return (
        parameters['//releases:root'] / \
        foreman.get_relpath() /
        name /
        ASSERT.not_none(parameters['%s/version' % name]) /
        shipyard2.IMAGE_DIR_IMAGE_FILENAME
    )


def parse_images_parameter(value):
    images = []
    for v in value.split(','):
        if v.startswith('id:'):
            images.append(models.PodConfig.Image(id=v[len('id:'):]))
        elif v.startswith('nv:'):
            _, name, version = v.split(':', maxsplit=3)
            images.append(models.PodConfig.Image(name=name, version=version))
        elif v.startswith('tag:'):
            images.append(models.PodConfig.Image(tag=v[len('tag:'):]))
        else:
            ASSERT.unreachable('unknown image parameter: {}', v)
    return images


def chown(path):
    user = getpass.getuser()
    with scripts.using_sudo():
        scripts.chown(
            user,
            grp.getgrgid(pwd.getpwnam(user).pw_gid).gr_name,
            path,
        )


def rsync(src_path, dst_path, rsync_args=()):
    scripts.run([
        'rsync',
        '--archive',
        *rsync_args,
        # Use the trailing slash trick.
        '%s/' % src_path,
        dst_path,
    ])
