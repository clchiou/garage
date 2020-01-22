__all__ = [
    'get_builder_name',
    'get_builder_image_path',
    'get_image_path',
    'parse_image_list_parameter',
    # Helper commands.
    'chown',
    'rsync',
    'sudo_rm',
]

import getpass

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

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


def parse_image_list_parameter(value):
    image_list = []
    for image in value.split(','):
        if image.startswith('id:'):
            image_list.append(('id', (image[len('id:'):], )))
        elif image.startswith('nv:'):
            _, name, version = image.split(':', maxsplit=3)
            image_list.append(('nv', (name, version)))
        elif image.startswith('tag:'):
            image_list.append(('tag', (image[len('tag:'):], )))
        else:
            ASSERT.unreachable('unknown image parameter: {}', image)
    return image_list


def chown(path):
    user = getpass.getuser()
    with scripts.using_sudo():
        scripts.chown(user, user, path)


def rsync(src_path, dst_path, rsync_args=()):
    scripts.run([
        'rsync',
        '--archive',
        *rsync_args,
        # Use the trailing slash trick.
        '%s/' % src_path,
        dst_path,
    ])


def sudo_rm(path):
    with scripts.using_sudo():
        scripts.rm(path, recursive=True)
