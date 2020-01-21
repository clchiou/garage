__all__ = [
    'get_builder_name',
    'get_builder_image_path',
    'get_image_path',
    'parse_image_list_parameter',
    # `ctr` wrappers.
    'ctr_build_image',
    'ctr_generate_pod_id',
    'ctr_get_rootfs_path',
    'ctr_import_image',
    'ctr',
    # Helper commands.
    'chown',
    'rsync',
    'sudo_rm',
]

import csv
import getpass
import shutil

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


def ctr_get_rootfs_path(kind, args):
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


def ctr_generate_pod_id():
    with scripts.doing_capture_output():
        return ctr(['pods', 'generate-id']).stdout.decode('utf8').strip()


def ctr(args):
    with scripts.using_sudo():
        return scripts.run([
            # Because sudo does not search into custom paths, let's look
            # it up before sudo.
            ASSERT.not_none(shutil.which('ctr')),
            *(('--verbose', ) if shipyard2.is_debug() else ()),
            *args,
        ])


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
